from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .adjustment_service import calculate_invoice_financial_position
from .late_fee_models import LateFee, LateFeePolicy
from .late_fee_service import calculate_late_fee, generate_late_fee
from .models import Invoice


class LateFeeEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("late-fee-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Late Fee Workspace", slug="late-fee-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Late Fee Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="101",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Late Fee Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 9, 10),
        )

    def make_policy(self, **overrides):
        values = {
            "workspace": self.workspace,
            "enabled": True,
            "grace_period_days": 0,
            "calculation_mode": LateFeePolicy.MODE_FIXED,
            "rate": Decimal("500.00"),
            "minimum_overdue_balance": Decimal("0.01"),
            "maximum_late_fee": None,
        }
        values.update(overrides)
        return LateFeePolicy.objects.create(**values)

    def test_late_fee_is_not_eligible_before_effective_date(self):
        policy = self.make_policy(grace_period_days=2)
        effective_date, fee, outstanding = calculate_late_fee(
            self.invoice, policy, date(2026, 9, 12)
        )
        self.assertEqual(effective_date, date(2026, 9, 13))
        self.assertEqual(fee, Decimal("0.00"))
        self.assertIsNone(outstanding)

    def test_late_fee_uses_base_receivable_without_compounding_prior_late_fee(self):
        policy = self.make_policy(
            calculation_mode=LateFeePolicy.MODE_PERCENTAGE,
            rate=Decimal("10.00"),
        )
        first, first_result = generate_late_fee(
            self.owner, self.workspace, self.invoice.id, as_of=date(2026, 9, 11)
        )
        self.assertIsNotNone(first)
        self.assertEqual(first.amount, Decimal("1000.00"))
        self.assertEqual(first.outstanding_balance, Decimal("10000.00"))
        self.assertEqual(first_result["outstanding"], Decimal("10000.00"))

        second_date, second_fee, second_outstanding = calculate_late_fee(
            self.invoice, policy, date(2026, 9, 12)
        )
        self.assertEqual(second_date, date(2026, 9, 11))
        self.assertEqual(second_fee, Decimal("1000.00"))
        self.assertEqual(second_outstanding, Decimal("10000.00"))

    def test_late_fee_recomputes_invoice_financial_state(self):
        policy = self.make_policy(rate=Decimal("500.00"))
        late_fee, result = generate_late_fee(
            self.owner, self.workspace, self.invoice.id, as_of=date(2026, 9, 11)
        )
        self.assertTrue(result["created"])
        self.assertEqual(late_fee.amount, Decimal("500.00"))

        self.invoice.refresh_from_db()
        position = calculate_invoice_financial_position(self.invoice)
        self.assertEqual(position["late_fee_total"], Decimal("500.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("10500.00"))
        self.assertEqual(position["outstanding"], Decimal("10500.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")

    def test_late_fee_does_not_apply_when_invoice_is_fully_settled(self):
        from .services import record_payment

        record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice,
                "amount": Decimal("10000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 10),
            },
        )
        policy = self.make_policy(rate=Decimal("500.00"))
        late_fee, result = generate_late_fee(
            self.owner, self.workspace, self.invoice.id, as_of=date(2026, 9, 11)
        )
        self.assertIsNone(late_fee)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["amount"], Decimal("0.00"))

    def test_late_fee_generation_is_idempotent_for_same_effective_date(self):
        policy = self.make_policy(rate=Decimal("500.00"))
        first, first_result = generate_late_fee(
            self.owner, self.workspace, self.invoice.id, as_of=date(2026, 9, 11)
        )
        second, second_result = generate_late_fee(
            self.owner, self.workspace, self.invoice.id, as_of=date(2026, 9, 12)
        )
        self.assertTrue(first_result["created"])
        self.assertFalse(second_result["created"])
        self.assertEqual(first.id, second.id)
        self.assertEqual(LateFee.objects.filter(invoice=self.invoice).count(), 1)

    def test_late_fee_policy_rejects_percentage_above_100(self):
        policy = self.make_policy(
            calculation_mode=LateFeePolicy.MODE_PERCENTAGE,
            rate=Decimal("101.00"),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()
