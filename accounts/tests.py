from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User


class AuthenticationSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"
        self.user = User.objects.create_user("owner@example.com", self.password)

    def test_protected_invoice_endpoint_requires_authentication(self):
        response = self.client.get("/api/invoices/")
        self.assertEqual(response.status_code, 401)

    def test_login_rejects_inactive_account(self):
        self.user.is_active_account = False
        self.user.save(update_fields=["is_active_account"])

        response = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(RESEND_API_KEY="test-key")
    @patch("accounts.api.resend.Emails.send")
    def test_forgot_password_has_same_response_for_unknown_email(self, send_mock):
        existing = self.client.post(
            "/api/forgot-password/",
            {"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            "/api/forgot-password/",
            {"email": "missing@example.com"},
            format="json",
        )

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(existing.data, unknown.data)
        send_mock.assert_called_once()

    def test_password_reset_revokes_outstanding_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        refresh_token = str(refresh)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": "NewStrongPass123!", "confirm_password": "NewStrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            BlacklistedToken.objects.filter(
                token__token=refresh_token
            ).exists()
        )
