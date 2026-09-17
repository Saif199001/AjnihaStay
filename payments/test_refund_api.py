from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from payments.models import Payment
from payments.refund_models import PaymentRefund
from workspaces.models import Membership, Workspace


class PaymentRefundAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="refund-api-owner@example.com", password="pass1234"
        )
        self.staff = User.objects.create_user(
            email="refund-api-staff@example.com", password="pass1234"
        )
        self.workspace = Workspace.objects.create(
            name="Refund API Workspace",
            slug="refund-api-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.staff, role=Membership.ROLE_VIEWER
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000.00"),
            payment_method="cash",
            payment_date=date(2026, 9, 5),
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.owner)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(self.workspace.id)

    def test_create_refund_api_delegates_to_canonical_service(self):
        self.authenticate()
        response = self.client.post(
            "/api/payments/refunds/create/",
            {"payment": self.payment.id, "amount": "100", "reason": "API refund"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_create_refund_rejects_invalid_payload(self):
        self.authenticate()
        response = self.client.post(
            "/api/payments/refunds/create/",
            {"payment": self.payment.id, "amount": "0", "reason": "Invalid"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_refund_returns_not_found_for_cross_workspace_payment(self):
        other_owner = User.objects.create_user(email="refund-api-other@example.com", password="pass1234")
        other_workspace = Workspace.objects.create(name="Other Refund API Workspace", slug="other-refund-api-workspace", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role=Membership.ROLE_OWNER)
        other_payment = Payment.objects.create(workspace=other_workspace, invoice=None, amount=Decimal("1000.00"), payment_method="cash", payment_date=date(2026, 9, 5))
        self.authenticate()
        response = self.client.post("/api/payments/refunds/create/", {"payment": other_payment.id, "amount": "100", "reason": "Wrong workspace"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_create_refund(self):
        self.authenticate(self.staff)
        response = self.client.post("/api/payments/refunds/create/", {"payment": self.payment.id, "amount": "100", "reason": "Unauthorized"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_transition_api_requires_failure_reason(self):
        self.authenticate()
        refund = PaymentRefund.objects.create(workspace=self.workspace, payment=self.payment, amount=Decimal("100"), reason="Test", idempotency_key="API-TRANSITION-1", requested_by=self.owner)
        response = self.client.post(f"/api/payments/refunds/{refund.id}/transition/", {"status": PaymentRefund.STATUS_FAILED}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_transition_api_returns_not_found_for_unknown_refund(self):
        self.authenticate()
        response = self.client.post("/api/payments/refunds/999999/transition/", {"status": PaymentRefund.STATUS_PROCESSING}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_transition_api_updates_refund_state(self):
        self.authenticate()
        refund = PaymentRefund.objects.create(workspace=self.workspace, payment=self.payment, amount=Decimal("100"), reason="Test", idempotency_key="API-TRANSITION-2", requested_by=self.owner)
        response = self.client.post(f"/api/payments/refunds/{refund.id}/transition/", {"status": PaymentRefund.STATUS_PROCESSING}, format="json")
        self.assertEqual(response.status_code, 200)
