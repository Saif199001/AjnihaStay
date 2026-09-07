from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import Invoice, PaymentAllocation
from payments.services import record_payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationCompatibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("compat-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Compatibility Workspace", slug="compatibility-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Compatibility Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Compatibility Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="C-1", rent=Decimal("5000.00")
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("5000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        self.invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 9, 30),
            rent_amount=Decimal("5000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 5),
        )
        self.second_invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 10, 1),
            billing_end=date(2026, 10, 31),
            rent_amount=Decimal("3000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 11, 5),
        )

    def payment_data(self, amount):
        return {
            "invoice": self.invoice.id,
            "amount": Decimal(amount),
            "payment_method": "upi",
            "payment_date": date(2026, 9, 7),
        }

    def test_record_payment_creates_matching_allocation(self):
        payment = record_payment(self.owner, self.workspace, self.payment_data("2000.00"))
        allocation = PaymentAllocation.objects.get(payment=payment)

        self.assertEqual(payment.invoice_id, self.invoice.id)
        self.assertEqual(allocation.invoice_id, self.invoice.id)
        self.assertEqual(allocation.amount, Decimal("2000.00"))
        self.assertEqual(
            payment.allocations.aggregate(total=Sum("amount"))["total"], Decimal("2000.00")
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("2000.00"))
        self.assertEqual(self.invoice.status, "partial")

    def test_legacy_linked_payment_cannot_be_allocated_to_another_invoice(self):
        payment = record_payment(self.owner, self.workspace, self.payment_data("2000.00"))

        with self.assertRaisesMessage(
            ValidationError,
            "A legacy invoice-linked payment can only be allocated to its linked invoice",
        ):
            allocate_payment(
                self.owner,
                self.workspace,
                payment,
                [{"invoice": self.second_invoice.id, "amount": "1000.00"}],
            )

        self.assertEqual(payment.allocations.count(), 1)
        self.assertEqual(payment.allocations.first().invoice_id, self.invoice.id)
        self.assertEqual(payment.allocations.first().amount, Decimal("2000.00"))
