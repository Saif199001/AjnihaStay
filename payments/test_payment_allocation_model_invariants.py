from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationModelInvariantTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("allocation-model@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Allocation Model Workspace",
            slug="allocation-model-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Allocation Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Allocation Property",
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
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.other_invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 2, 1),
            billing_end=date(2026, 2, 28),
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 3, 5),
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("1000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 10),
        )

    def test_direct_orm_create_rejects_payment_over_allocation(self):
        PaymentAllocation.objects.create(
            payment=self.payment,
            invoice=self.invoice,
            amount=Decimal("700.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Allocation exceeds payment amount"):
            PaymentAllocation.objects.create(
                payment=self.payment,
                invoice=self.other_invoice,
                amount=Decimal("300.01"),
            )

        self.assertEqual(self.payment.allocations.count(), 1)
        self.assertEqual(self.payment.allocations.first().amount, Decimal("700.00"))

    def test_direct_orm_create_rejects_invoice_over_allocation(self):
        other_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("500.00"),
            payment_method="cash",
            payment_date=date(2026, 9, 10),
        )
        PaymentAllocation.objects.create(
            payment=other_payment,
            invoice=self.invoice,
            amount=Decimal("900.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Allocation exceeds invoice remaining amount"):
            PaymentAllocation.objects.create(
                payment=self.payment,
                invoice=self.invoice,
                amount=Decimal("100.01"),
            )

        self.assertEqual(self.invoice.allocations.count(), 1)
        self.assertEqual(self.invoice.allocations.first().amount, Decimal("900.00"))

    def test_direct_orm_create_rejects_legacy_payment_wrong_invoice(self):
        linked_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            amount=Decimal("100.00"),
            payment_method="cash",
            payment_date=date(2026, 9, 10),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "A legacy invoice-linked payment can only be allocated to its linked invoice",
        ):
            PaymentAllocation.objects.create(
                payment=linked_payment,
                invoice=self.other_invoice,
                amount=Decimal("100.00"),
            )

        self.assertEqual(linked_payment.allocations.count(), 0)

    def test_direct_orm_create_accepts_allocation_within_both_capacities(self):
        allocation = PaymentAllocation.objects.create(
            payment=self.payment,
            invoice=self.invoice,
            amount=Decimal("1000.00"),
        )

        self.assertEqual(allocation.amount, Decimal("1000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("0"))
        self.assertEqual(self.invoice.allocated_paid_amount, Decimal("1000.00"))
