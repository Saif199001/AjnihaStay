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
            email="refund-api-staff@example.com", password="pass1234", role="staff"
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
            workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF
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
            f"/api/payments/{self.payment.id}/refunds/",
            {
                "amount": "2500.00",
                "reason": "Customer overpayment",
                "reference": "REF-API-1",
                "idempotency_key": "refund-api-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["amount"], "2500.00")
        self.assertEqual(response.data["data"]["status"], PaymentRefund.STATUS_REQUESTED)
        self.assertEqual(response.data["data"]["payment"], self.payment.id)

    def test_create_refund_rejects_invalid_payload(self):
        self.authenticate()
        response = self.client.post(
            f"/api/payments/{self.payment.id}/refunds/",
            {"amount": "0", "reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data)
        self.assertIn("reason", response.data)

    def test_create_refund_returns_not_found_for_cross_workspace_payment(self):
        self.authenticate()
        other_owner = User.objects.create_user(
            email="refund-api-other@example.com", password="pass1234"
        )
        other_workspace = Workspace.objects.create(
            name="Other Refund API Workspace",
            slug="other-refund-api-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace, user=other_owner, role=Membership.ROLE_OWNER
        )
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(other_workspace.id)
        response = self.client.post(
            f"/api/payments/{self.payment.id}/refunds/",
            {"amount": "100", "reason": "Wrong workspace"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Payment not found")

    def test_staff_cannot_create_refund(self):
        self.authenticate(self.staff)
        response = self.client.post(
            f"/api/payments/{self.payment.id}/refunds/",
            {"amount": "100", "reason": "Unauthorized"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_transition_api_updates_refund_state(self):
        self.authenticate()
        refund = PaymentRefund.objects.create(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("500.00"),
            reason="Transition test",
            requested_by=self.owner,
        )
        response = self.client.patch(
            f"/api/payment-refunds/{refund.id}/",
            {"status": PaymentRefund.STATUS_PROCESSING},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], PaymentRefund.STATUS_PROCESSING)

    def test_transition_api_requires_failure_reason(self):
        self.authenticate()
        refund = PaymentRefund.objects.create(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("500.00"),
            reason="Failure test",
            requested_by=self.owner,
        )
        response = self.client.patch(
            f"/api/payment-refunds/{refund.id}/",
            {"status": PaymentRefund.STATUS_FAILED},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Refund failure reason is required")

    def test_transition_api_returns_not_found_for_unknown_refund(self):
        self.authenticate()
        response = self.client.patch(
            "/api/payment-refunds/999999/",
            {"status": PaymentRefund.STATUS_PROCESSING},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Refund not found")
