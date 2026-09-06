from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("allocation-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("allocation-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Allocation Workspace",
            slug="allocation-workspace",
            owner=self.owner,
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Workspace",
            slug="other-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Tenant One",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Property One",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="A-1",
            rent=Decimal("10000.00"),
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        self.invoice_a = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("6000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.invoice_b = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 2, 1),
            billing_end=date(2026, 2, 28),
            rent_amount=Decimal("4000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 3, 5),
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 6),
        )

    def test_allocates_one_payment_across_multiple_invoices(self):
        allocations = allocate_payment(
            None,
            self.workspace,
            self.payment,
            [
                {"invoice": self.invoice_a.id, "amount": Decimal("6000")},
                {"invoice": self.invoice_b.id, "amount": Decimal("4000")},
            ],
        )

        self.assertEqual(len(allocations), 2)
        self.assertEqual(
            self.payment.allocations.aggregate(total=Sum("amount"))["total"],
            Decimal("10000"),
        )
        self.assertEqual(Invoice.objects.get(id=self.invoice_a.id).status, "paid")
        self.assertEqual(Invoice.objects.get(id=self.invoice_b.id).status, "paid")

    def test_rejects_payment_over_allocation(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice_a.id, "amount": Decimal("10001")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_invoice_over_allocation(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice_a.id, "amount": Decimal("6001")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_duplicate_invoice_entries(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [
                    {"invoice": self.invoice_a.id, "amount": Decimal("1000")},
                    {"invoice": self.invoice_a.id, "amount": Decimal("1000")},
                ],
            )

    def test_rejects_cross_workspace_invoice(self):
        other_tenant = Tenant.objects.create(
            owner=self.other_owner,
            workspace=self.other_workspace,
            full_name="Other",
            phone="8888888888",
            permanent_address="Delhi",
        )
        other_property = Property.objects.create(
            owner=self.other_owner,
            workspace=self.other_workspace,
            name="Other Property",
            property_type="pg",
            address="Other Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        other_unit = Unit.objects.create(
            property=other_property,
            unit_type="room",
            unit_number="B-1",
            rent=Decimal("1000.00"),
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            allotted_by=self.other_owner,
            rent=Decimal("1000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        other_invoice = Invoice.objects.create(
            occupancy=other_occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": other_invoice.id, "amount": Decimal("1000")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_partial_allocation_updates_invoice_state(self):
        allocate_payment(
            None,
            self.workspace,
            self.payment,
            [{"invoice": self.invoice_a.id, "amount": Decimal("2500")}],
        )
        invoice = Invoice.objects.get(id=self.invoice_a.id)
        self.assertEqual(invoice.paid_amount, Decimal("2500"))
        self.assertEqual(invoice.status, "partial")
        self.assertEqual(self.payment.unallocated_amount, Decimal("7500"))
