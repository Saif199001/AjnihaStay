from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .final_settlement import FinalSettlement, finalize_final_settlement
from .models import Invoice, Payment
from .services import calculate_final_settlement, record_payment


class FinalSettlementLifecycleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("settlement-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("settlement-other@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("settlement-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("settlement-staff@example.com", "StrongPass123!")

        self.workspace = Workspace.objects.create(
            name="Settlement Workspace", slug="settlement-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Settlement Workspace", slug="other-settlement-workspace", owner=self.other_owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Settlement Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="301", rent=Decimal("10000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Settlement Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1), security_deposit=Decimal("5000.00"), deposit_paid=True,
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 9, 30),
        )
        self.client = APIClient()

    def settle_invoice(self):
        return record_payment(self.owner, self.workspace, {
            "invoice": self.invoice.id,
            "amount": Decimal("10000.00"),
            "payment_method": "upi",
            "payment_date": date(2026, 9, 30),
        })

    def test_checkout_date_is_required(self):
        self.occupancy.check_out_date = None
        Occupancy.objects.filter(pk=self.occupancy.pk).update(check_out_date=None)
        with self.assertRaisesMessage(ValidationError, "Occupancy must have a check-out date before final settlement"):
            finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        self.assertFalse(FinalSettlement.objects.filter(occupancy=self.occupancy).exists())

    def test_outstanding_invoice_blocks_finalization(self):
        with self.assertRaisesMessage(ValidationError, "Final settlement requires all outstanding invoices to be settled"):
            finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        self.assertFalse(FinalSettlement.objects.filter(occupancy=self.occupancy).exists())

    def test_full_deposit_refund_creates_full_refund_outcome(self):
        self.settle_invoice()
        settlement = finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        self.assertEqual(settlement.outcome, FinalSettlement.OUTCOME_FULL_REFUND)
        self.assertEqual(settlement.security_deposit, Decimal("5000.00"))
        self.assertEqual(settlement.refundable_deposit, Decimal("5000.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("0.00"))
        self.assertEqual(settlement.total_due, Decimal("0.00"))
        self.occupancy.refresh_from_db()
        self.assertTrue(self.occupancy.is_active)

    def test_full_retention_is_explicit_and_not_inferred_from_balance(self):
        self.settle_invoice()
        settlement = finalize_final_settlement(
            self.owner, self.workspace, self.occupancy.id, refundable_deposit=Decimal("0.00")
        )
        self.assertEqual(settlement.outcome, FinalSettlement.OUTCOME_FULL_RETENTION)
        self.assertEqual(settlement.refundable_deposit, Decimal("0.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("5000.00"))
        self.assertEqual(settlement.final_balance, Decimal("-5000.00"))

    def test_partial_refund_and_retention(self):
        self.settle_invoice()
        settlement = finalize_final_settlement(
            self.owner, self.workspace, self.occupancy.id, refundable_deposit=Decimal("3000.00")
        )
        self.assertEqual(settlement.outcome, FinalSettlement.OUTCOME_PARTIAL_REFUND)
        self.assertEqual(settlement.refundable_deposit, Decimal("3000.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("2000.00"))

    def test_no_deposit_has_no_deposit_outcome(self):
        self.occupancy.security_deposit = Decimal("0.00")
        Occupancy.objects.filter(pk=self.occupancy.pk).update(security_deposit=Decimal("0.00"))
        self.settle_invoice()
        settlement = finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        self.assertEqual(settlement.outcome, FinalSettlement.OUTCOME_NO_DEPOSIT)
        self.assertEqual(settlement.refundable_deposit, Decimal("0.00"))
        self.assertEqual(settlement.retained_deposit, Decimal("0.00"))

    def test_refundable_deposit_cannot_exceed_security_deposit(self):
        self.settle_invoice()
        with self.assertRaisesMessage(ValidationError, "Refundable deposit must be between zero and the security deposit"):
            finalize_final_settlement(self.owner, self.workspace, self.occupancy.id, Decimal("5000.01"))

    def test_refundable_deposit_cannot_be_negative(self):
        self.settle_invoice()
        with self.assertRaisesMessage(ValidationError, "Refundable deposit must be between zero and the security deposit"):
            finalize_final_settlement(self.owner, self.workspace, self.occupancy.id, Decimal("-0.01"))

    def test_retry_is_idempotent_and_returns_same_snapshot(self):
        self.settle_invoice()
        first = finalize_final_settlement(self.owner, self.workspace, self.occupancy.id, Decimal("3000.00"))
        second = finalize_final_settlement(self.owner, self.workspace, self.occupancy.id, Decimal("0.00"))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.refundable_deposit, Decimal("3000.00"))
        self.assertEqual(FinalSettlement.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_snapshot_is_immutable(self):
        self.settle_invoice()
        settlement = finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        settlement.outcome = FinalSettlement.OUTCOME_FULL_RETENTION
        with self.assertRaisesMessage(ValidationError, "Final settlement facts cannot be changed after settlement"):
            settlement.save()

    def test_cross_workspace_occupancy_is_blocked(self):
        with self.assertRaisesMessage(ValidationError, "Occupancy not found"):
            finalize_final_settlement(self.other_owner, self.other_workspace, self.occupancy.id)

    def test_staff_cannot_finalize_financial_settlement(self):
        with self.assertRaisesMessage(PermissionDenied, "Financial mutation requires manager-level access"):
            finalize_final_settlement(self.staff, self.workspace, self.occupancy.id)

    def test_manager_can_finalize_settlement(self):
        self.settle_invoice()
        settlement = finalize_final_settlement(self.manager, self.workspace, self.occupancy.id)
        self.assertEqual(settlement.settled_by_id, self.manager.id)

    def test_finalization_does_not_create_payment_refund(self):
        self.settle_invoice()
        finalize_final_settlement(self.owner, self.workspace, self.occupancy.id)
        self.assertFalse(Payment.objects.filter(invoice=self.invoice).count() == 0)
        from .refund_models import PaymentRefund
        self.assertEqual(PaymentRefund.objects.count(), 0)

    def test_existing_get_final_settlement_projection_is_unchanged(self):
        expected = calculate_final_settlement(self.occupancy.id, self.workspace)
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            f"/api/final-settlement/{self.occupancy.id}/",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], expected)

    def test_post_finalization_api_uses_canonical_transition(self):
        self.settle_invoice()
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            f"/api/final-settlement/{self.occupancy.id}/settle/",
            {},
            format="json",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["outcome"], FinalSettlement.OUTCOME_FULL_REFUND)

    def test_final_settlement_table_has_workspace_rls_on_postgresql(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS validation is PostgreSQL-specific")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = %s::regclass",
                ["payments_finalsettlement"],
            )
            enabled, forced = cursor.fetchone()
            self.assertTrue(enabled)
            self.assertTrue(forced)
            cursor.execute(
                "SELECT 1 FROM pg_policies WHERE schemaname = current_schema() "
                "AND tablename = 'payments_finalsettlement' "
                "AND policyname = 'workspace_isolation_payments_finalsettlement'"
            )
            self.assertIsNotNone(cursor.fetchone())
