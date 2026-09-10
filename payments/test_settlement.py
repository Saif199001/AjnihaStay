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
from .settlement_models import OccupancySettlement
from .settlement_service import settle_occupancy


class OccupancySettlementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("settlement-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("settlement-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Settlement Workspace", slug="settlement-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Settlement Workspace", slug="other-settlement-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        property_obj = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Settlement Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="S-101", rent=Decimal("10000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Settlement Tenant", phone="9999999999", permanent_address="Delhi")
        self.occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 8, 1), check_out_date=date(2026, 8, 31), next_due_date=date(2026, 9, 1), security_deposit=Decimal("5000.00"))
        self.invoice = Invoice.objects.create(occupancy=self.occupancy, billing_start=date(2026, 8, 1), billing_end=date(2026, 8, 31), rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 8, 10))

    def test_settlement_requires_zero_canonical_invoice_balance(self):
        with self.assertRaisesMessage(ValidationError, "Occupancy has outstanding invoice balance"):
            settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_REFUND, Decimal("5000.00"))

    def test_full_refund_settlement_records_deposit_without_creating_payment(self):
        from .services import record_payment
        record_payment(self.owner, self.workspace, {"invoice": self.invoice, "amount": Decimal("10000.00"), "payment_method": "upi", "payment_date": date(2026, 8, 5)})
        settlement, created = settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_REFUND, Decimal("5000.00"))
        self.assertTrue(created)
        self.assertEqual(settlement.invoice_outstanding, Decimal("0.00"))
        self.assertEqual(settlement.refundable_deposit, Decimal("5000.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("0.00"))
        self.assertEqual(self.invoice.payments.count(), 1)

    def test_partial_refund_and_retention_are_explicit(self):
        from .services import record_payment
        record_payment(self.owner, self.workspace, {"invoice": self.invoice, "amount": Decimal("10000.00"), "payment_method": "upi", "payment_date": date(2026, 8, 5)})
        settlement, created = settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_PARTIAL_REFUND, Decimal("3000.00"))
        self.assertTrue(created)
        self.assertEqual(settlement.refundable_deposit, Decimal("3000.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("2000.00"))

    def test_settlement_is_idempotent(self):
        from .services import record_payment
        record_payment(self.owner, self.workspace, {"invoice": self.invoice, "amount": Decimal("10000.00"), "payment_method": "upi", "payment_date": date(2026, 8, 5)})
        first, created = settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_RETENTION, Decimal("0.00"))
        second, replayed = settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_RETENTION, Decimal("0.00"))
        self.assertTrue(created)
        self.assertFalse(replayed)
        self.assertEqual(first.id, second.id)
        self.assertEqual(OccupancySettlement.objects.count(), 1)

    def test_cross_workspace_settlement_is_blocked(self):
        with self.assertRaisesMessage(ValidationError, "Occupancy not found"):
            settle_occupancy(self.other_owner, self.other_workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_REFUND, Decimal("5000.00"))

    def test_settlement_facts_are_immutable(self):
        from .services import record_payment
        record_payment(self.owner, self.workspace, {"invoice": self.invoice, "amount": Decimal("10000.00"), "payment_method": "upi", "payment_date": date(2026, 8, 5)})
        settlement, _ = settle_occupancy(self.owner, self.workspace, self.occupancy.id, OccupancySettlement.OUTCOME_FULL_REFUND, Decimal("5000.00"))
        settlement.refundable_deposit = Decimal("1000.00")
        with self.assertRaisesMessage(ValidationError, "Settlement financial facts cannot be changed after creation"):
            settlement.save()
