from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Invoice
from .services import create_payment


class PaymentIntegrityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Owner Workspace", slug="owner-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Test Property", property_type="pg",
            address="Test Address", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="101", rent=Decimal("10000.00"))
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Test Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1),
        )

    def payment_data(self, amount):
        return {
            "invoice": self.invoice.id, "amount": Decimal(amount), "payment_method": "upi",
            "payment_date": date(2026, 9, 3),
        }

    def test_payment_cannot_overpay_invoice(self):
        create_payment(self.owner, self.workspace, self.payment_data("7000.00"))
        with self.assertRaises(ValidationError):
            create_payment(self.owner, self.workspace, self.payment_data("4000.00"))

    def test_payment_is_workspace_scoped(self):
        with self.assertRaises(ValidationError):
            create_payment(self.other_owner, self.other_workspace, self.payment_data("1000.00"))

    def test_payment_updates_invoice_balance(self):
        create_payment(self.owner, self.workspace, self.payment_data("4000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(self.invoice.due_amount, Decimal("6000.00"))

    def test_full_payment_marks_invoice_paid(self):
        create_payment(self.owner, self.workspace, self.payment_data("10000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.due_amount, Decimal("0.00"))
