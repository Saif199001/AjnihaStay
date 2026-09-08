from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice, Payment
from payments.refund_models import PaymentRefund
from payments.refund_service import request_payment_refund, transition_payment_refund
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Workspace


class PaymentRefundServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="refund-owner", email="refund-owner@example.com", password="pass1234"
        )
        self.manager = User.objects.create_user(
            username="refund-manager", email="refund-manager@example.com", password="pass1234"
        )
        self.manager.role = "manager"
        self.manager.save(update_fields=["role"])
        self.other_user = User.objects.create_user(
            username="refund-user", email="refund-user@example.com", password="pass1234"
        )

        self.workspace = Workspace.objects.create(name="Refund Workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", owner=self.owner)
        self.tenant = Tenant.objects.create(workspace=self.workspace, full_name="Refund Tenant")
        self.property = Property.objects.create(workspace=self.workspace, name="Refund Property")
        self.unit = Unit.objects.create(property=self.property, unit_number="R-101", rent=Decimal("10000"))
        self.occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit)
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start="2026-09-01",
            billing_end="2026-09-30",
            rent_amount=Decimal("10000"),
            charges_amount=Decimal("0"),
            due_date="2026-09-05",
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            amount=Decimal("10000"),
            payment_method="cash",
            payment_date="2026-09-05",
        )

    def test_request_creates_requested_refund(self):
        refund = request_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            payment=self.payment,
            amount="2500",
            reason="Customer overpayment",
        )
        self.assertEqual(refund.status, PaymentRefund.STATUS_REQUESTED)
        self.assertEqual(refund.amount, Decimal("2500.00"))
        self.assertEqual(refund.payment_id, self.payment.id)

    def test_successful_refund_consumes_capacity(self):
        refund = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="4000", reason="Partial refund"
        )
        transition_payment_refund(
            user=self.owner, workspace=self.workspace, refund=refund,
            status=PaymentRefund.STATUS_PROCESSING
        )
        transition_payment_refund(
            user=self.owner, workspace=self.workspace, refund=refund,
            status=PaymentRefund.STATUS_SUCCEEDED
        )
        second = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="6000", reason="Remaining refund"
        )
        self.assertEqual(second.amount, Decimal("6000.00"))
        with self.assertRaises(ValidationError):
            request_payment_refund(
                user=self.owner, workspace=self.workspace, payment=self.payment,
                amount="1", reason="Excess refund"
            )

    def test_active_refund_reserves_capacity(self):
        request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="7000", reason="Pending refund"
        )
        with self.assertRaises(ValidationError):
            request_payment_refund(
                user=self.owner, workspace=self.workspace, payment=self.payment,
                amount="3001", reason="Over capacity"
            )

    def test_failed_refund_releases_capacity(self):
        refund = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="7000", reason="Refund attempt"
        )
        transition_payment_refund(
            user=self.owner, workspace=self.workspace, refund=refund,
            status=PaymentRefund.STATUS_FAILED, failure_reason="Gateway rejected"
        )
        replacement = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="7000", reason="Retry refund"
        )
        self.assertEqual(replacement.status, PaymentRefund.STATUS_REQUESTED)

    def test_idempotency_returns_existing_refund_for_same_operation(self):
        first = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="1500", reason="Duplicate-safe", idempotency_key="refund-1"
        )
        second = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="1500", reason="Duplicate-safe retry", idempotency_key="refund-1"
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(PaymentRefund.objects.filter(idempotency_key="refund-1").count(), 1)

    def test_idempotency_conflict_is_rejected(self):
        request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="1500", reason="Original", idempotency_key="refund-conflict"
        )
        with self.assertRaises(ValidationError):
            request_payment_refund(
                user=self.owner, workspace=self.workspace, payment=self.payment,
                amount="1600", reason="Different operation", idempotency_key="refund-conflict"
            )

    def test_unauthorized_user_cannot_request_refund(self):
        with self.assertRaises(ValidationError):
            request_payment_refund(
                user=self.other_user, workspace=self.workspace, payment=self.payment,
                amount="100", reason="Unauthorized"
            )

    def test_manager_can_request_refund(self):
        refund = request_payment_refund(
            user=self.manager, workspace=self.workspace, payment=self.payment,
            amount="100", reason="Manager refund"
        )
        self.assertEqual(refund.requested_by_id, self.manager.id)

    def test_cross_workspace_payment_is_rejected(self):
        with self.assertRaises(ValidationError):
            request_payment_refund(
                user=self.owner, workspace=self.other_workspace, payment=self.payment,
                amount="100", reason="Wrong workspace"
            )

    def test_payment_and_allocations_are_not_mutated(self):
        original_amount = self.payment.amount
        refund = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="500", reason="No payment mutation"
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, original_amount)
        self.assertEqual(refund.payment_id, self.payment.id)

    def test_state_transitions_and_failure_reason(self):
        refund = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="500", reason="State test"
        )
        transition_payment_refund(
            user=self.owner, workspace=self.workspace, refund=refund,
            status=PaymentRefund.STATUS_PROCESSING
        )
        self.assertEqual(refund.status, PaymentRefund.STATUS_PROCESSING)
        transition_payment_refund(
            user=self.owner, workspace=self.workspace, refund=refund,
            status=PaymentRefund.STATUS_SUCCEEDED
        )
        with self.assertRaises(ValidationError):
            transition_payment_refund(
                user=self.owner, workspace=self.workspace, refund=refund,
                status=PaymentRefund.STATUS_FAILED, failure_reason="Too late"
            )

    def test_failed_transition_requires_failure_reason(self):
        refund = request_payment_refund(
            user=self.owner, workspace=self.workspace, payment=self.payment,
            amount="500", reason="Failure test"
        )
        with self.assertRaises(ValidationError):
            transition_payment_refund(
                user=self.owner, workspace=self.workspace, refund=refund,
                status=PaymentRefund.STATUS_FAILED
            )
