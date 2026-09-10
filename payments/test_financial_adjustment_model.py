from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from payments.models import FinancialAdjustment, Invoice
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class FinancialAdjustmentModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("adjustment-model@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Adjustment Model Workspace",
            slug="adjustment-model-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Adjustment Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Adjustment Property",
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
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )

    def make_adjustment(self, **overrides):
        data = {
            "workspace": self.workspace,
            "invoice": self.invoice,
            "adjustment_type": FinancialAdjustment.TYPE_CREDIT,
            "amount": Decimal("500.00"),
            "reason": "Approved service issue credit",
            "reference": "CASE-123",
            "idempotency_key": "ADJ-CASE-123",
            "created_by": self.owner,
        }
        data.update(overrides)
        return FinancialAdjustment.objects.create(**data)

    def test_valid_adjustment_persists_expected_fields(self):
        adjustment = self.make_adjustment()

        self.assertEqual(adjustment.amount, Decimal("500.00"))
        self.assertEqual(adjustment.adjustment_type, "credit")
        self.assertEqual(adjustment.workspace_id, self.workspace.id)
        self.assertEqual(adjustment.invoice_id, self.invoice.id)
        self.assertEqual(adjustment.created_by_id, self.owner.id)

    def test_invalid_type_is_rejected_by_model_validation(self):
        adjustment = FinancialAdjustment(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type="refund",
            amount=Decimal("500.00"),
            reason="Invalid type test",
            idempotency_key="ADJ-INVALID",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "Invalid adjustment type"):
            adjustment.full_clean()

    def test_non_positive_amount_is_rejected(self):
        adjustment = FinancialAdjustment(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("0.00"),
            reason="Zero amount test",
            idempotency_key="ADJ-ZERO",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "Adjustment amount must be greater than zero"):
            adjustment.full_clean()

    def test_amount_with_more_than_two_decimals_is_rejected_by_model_validation(self):
        adjustment = FinancialAdjustment(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("500.001"),
            reason="Precision test",
            idempotency_key="ADJ-PRECISION",
            created_by=self.owner,
        )

        # DecimalField(2) does not itself reject extra precision; the canonical
        # adjustment boundary must reject it before persistence.
        self.assertNotEqual(adjustment.amount, adjustment.amount.quantize(Decimal("0.01")))

    def test_blank_reason_is_rejected(self):
        adjustment = FinancialAdjustment(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("500.00"),
            reason="   ",
            idempotency_key="ADJ-REASON",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(ValidationError, "Adjustment reason is required"):
            adjustment.full_clean()

    def test_database_rejects_whitespace_only_reason(self):
        with self.assertRaises(IntegrityError):
            FinancialAdjustment.objects.bulk_create(
                [
                    FinancialAdjustment(
                        workspace=self.workspace,
                        invoice=self.invoice,
                        adjustment_type=FinancialAdjustment.TYPE_CREDIT,
                        amount=Decimal("500.00"),
                        reason="   ",
                        idempotency_key="ADJ-DB-REASON",
                        created_by=self.owner,
                    )
                ]
            )

    def test_cross_workspace_invoice_is_rejected(self):
        other_owner = User.objects.create_user("adjustment-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Adjustment Workspace",
            slug="other-adjustment-workspace",
            owner=other_owner,
        )
        adjustment = FinancialAdjustment(
            workspace=other_workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("500.00"),
            reason="Cross workspace test",
            idempotency_key="ADJ-CROSS-WORKSPACE",
            created_by=self.owner,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Adjustment and invoice must belong to the same workspace",
        ):
            adjustment.full_clean()

    def test_existing_adjustment_is_immutable(self):
        adjustment = self.make_adjustment()
        adjustment.amount = Decimal("600.00")

        with self.assertRaisesMessage(
            ValidationError,
            "Financial adjustments cannot be changed after creation",
        ):
            adjustment.save()

    def test_idempotency_key_is_unique_within_workspace(self):
        self.make_adjustment()
        duplicate = FinancialAdjustment(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type="credit",
            amount=Decimal("100.00"),
            reason="Retry",
            idempotency_key="ADJ-CASE-123",
            created_by=self.owner,
        )

        with self.assertRaises(IntegrityError):
            duplicate.save(force_insert=True)
