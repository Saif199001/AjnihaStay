from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import User
from payments.adjustment_service import create_financial_adjustment
from payments.models import FinancialAdjustment, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class FinancialAdjustmentServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("adjustment-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Adjustment Service Workspace",
            slug="adjustment-service-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Adjustment Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Adjustment Property",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property, unit_type="room", unit_number="A-1", rent=Decimal("10000.00"),
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1), next_due_date=date(2026, 2, 1),
            billing_type="arrears", billing_cycle="monthly",
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 1, 1), billing_end=date(2026, 1, 31),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 2, 5),
        )

    def create_adjustment(self, amount="1000.00", idempotency_key="ADJ-CASE-123"):
        return create_financial_adjustment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "adjustment_type": "credit",
                "amount": amount,
                "reason": "Test adjustment",
                "idempotency_key": idempotency_key,
            },
        )

    def test_idempotent_retry_returns_existing_adjustment(self):
        first, first_position, created = self.create_adjustment()
        second, second_position, created_again = self.create_adjustment()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first_position["adjusted_receivable"], second_position["adjusted_receivable"])
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_idempotency_key_cannot_be_reused_for_different_operation(self):
        self.create_adjustment()
        with self.assertRaisesMessage(ValidationError, "Idempotency key already used for a different adjustment"):
            self.create_adjustment(amount="1100.00")
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_service_requires_manager_level_membership(self):
        staff = User.objects.create_user("adjustment-staff@example.com", "StrongPass123!")
        Membership.objects.create(workspace=self.workspace, user=staff, role=Membership.ROLE_STAFF)
        with self.assertRaisesMessage(PermissionDenied, "Financial mutation requires manager-level access"):
            create_financial_adjustment(
                staff,
                self.workspace,
                {
                    "invoice": self.invoice.id,
                    "adjustment_type": "credit",
                    "amount": "100.00",
                    "reason": "Staff attempt",
                },
            )

    def test_cross_workspace_invoice_is_not_visible_to_service(self):
        other_owner = User.objects.create_user("adjustment-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Adjustment Service Workspace",
            slug="other-adjustment-service-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role=Membership.ROLE_OWNER)
        with self.assertRaisesMessage(ValidationError, "Invoice not found"):
            create_financial_adjustment(
                other_owner,
                other_workspace,
                {
                    "invoice": self.invoice.id,
                    "adjustment_type": "credit",
                    "amount": "100.00",
                    "reason": "Cross workspace",
                },
            )
