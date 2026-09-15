from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from accounts.models import User
from payments.advance_credit_service import apply_advance_credit, create_advance_credit
from payments.allocation_service import allocate_payment
from payments.models import AdvanceCreditApplication, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class AdvanceCreditHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("advance-hardening@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Advance Hardening Workspace",
            slug="advance-hardening-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Hardening Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Hardening Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="H-1",
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
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 8),
        )

    def create_credit(self, amount):
        return create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": amount,
            },
        )

    def test_reserved_credit_capacity_cannot_be_reallocated(self):
        credit = self.create_credit("4000")

        allocate_payment(
            self.owner,
            self.workspace,
            self.payment,
            [{"invoice": self.invoice.id, "amount": "6000"}],
        )

        with self.assertRaisesMessage(ValidationError, "Allocation exceeds payment amount"):
            allocate_payment(
                self.owner,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice.id, "amount": "1"}],
            )

        self.payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(credit.available_amount, Decimal("4000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("6000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.payment).count(), 1)

    def test_allocation_preserves_existing_credit_application_in_invoice_state(self):
        credit = self.create_credit("5000")
        apply_advance_credit(
            self.owner,
            self.workspace,
            {"credit": credit.id, "invoice": self.invoice.id, "amount": "5000"},
        )

        second_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("5000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 8),
        )
        allocate_payment(
            self.owner,
            self.workspace,
            second_payment,
            [{"invoice": self.invoice.id, "amount": "5000"}],
        )

        self.invoice.refresh_from_db()
        self.assertEqual(
            AdvanceCreditApplication.objects.filter(credit=credit).aggregate(total=Sum("amount"))["total"],
            Decimal("5000.00"),
        )
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.due_amount, Decimal("0.00"))

    def test_allocation_rejects_amount_above_combined_invoice_outstanding(self):
        credit = self.create_credit("7000")
        apply_advance_credit(
            self.owner,
            self.workspace,
            {"credit": credit.id, "invoice": self.invoice.id, "amount": "7000"},
        )

        second_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("5000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 8),
        )
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds invoice remaining amount"):
            allocate_payment(
                self.owner,
                self.workspace,
                second_payment,
                [{"invoice": self.invoice.id, "amount": "3000.01"}],
            )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("7000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(PaymentAllocation.objects.filter(payment=second_payment).count(), 0)

