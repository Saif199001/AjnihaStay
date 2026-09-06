from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice, Payment
from payments.services import record_payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class DirectFinancialMutationBoundaryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("boundary@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Boundary Workspace",
            slug="boundary-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Boundary Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="B-101",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Boundary Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 1),
        )

    def _payment(self, amount="4000.00"):
        return record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": Decimal(amount),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 6),
            },
        )

    def test_direct_invoice_paid_state_forgery_is_rejected(self):
        self._payment()
        self.invoice.refresh_from_db()
        self.invoice.paid_amount = Decimal("9999.00")
        self.invoice.status = "paid"

        with self.assertRaisesMessage(
            ValidationError,
            "Invoice paid amount and status are managed by the canonical financial service",
        ):
            self.invoice.save()

    def test_direct_invoice_financial_terms_cannot_change_after_payment(self):
        self._payment()
        self.invoice.refresh_from_db()
        self.invoice.rent_amount = Decimal("9000.00")

        with self.assertRaisesMessage(
            ValidationError,
            "Invoice financial terms cannot be changed after payments exist",
        ):
            self.invoice.save()

    def test_direct_payment_amount_cannot_change_after_creation(self):
        payment = self._payment()
        payment.amount = Decimal("5000.00")

        with self.assertRaisesMessage(
            ValidationError,
            "Payment invoice and amount cannot be changed after creation",
        ):
            payment.save()

        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("4000.00"))

    def test_direct_payment_invoice_cannot_change_after_creation(self):
        payment = self._payment()
        other_invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 10, 1),
            billing_end=date(2026, 11, 1),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 11, 1),
        )
        payment.invoice = other_invoice

        with self.assertRaisesMessage(
            ValidationError,
            "Payment invoice and amount cannot be changed after creation",
        ):
            payment.save()

        payment.refresh_from_db()
        self.assertEqual(payment.invoice_id, self.invoice.id)

    def test_canonical_payment_transition_remains_authoritative(self):
        payment = self._payment("10000.00")
        self.invoice.refresh_from_db()

        self.assertEqual(payment.amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
