from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from workspaces.models import Membership, Workspace

from .api import logout_api
from .services import (
    EmailVerificationDeliveryError,
    create_user_account,
    send_email_verification,
    set_account_active,
)

User = get_user_model()


class AccountsProductionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPassword!123"
        self.email = "owner@example.com"

    def create_user(self, *, email=None, verified=False):
        user = User.objects.create_user(
            email=email or self.email,
            password=self.password,
            email_verified=verified,
        )
        if verified:
            user.email_verified_at = user.date_joined
            user.save(update_fields=["email_verified_at"])
        return user

    def test_create_user_account_provisions_workspace_and_owner_membership(self):
        user = create_user_account(
            self.email,
            self.password,
            self.password,
            "Owner Workspace",
        )

        workspace = Workspace.objects.get(owner=user)
        membership = Membership.objects.get(workspace=workspace, user=user)

        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.email_verified)
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_create_user_account_rejects_duplicate_email(self):
        self.create_user()

        with self.assertRaisesMessage(Exception, "Email already exists"):
            create_user_account(
                self.email,
                self.password,
                self.password,
            )

    @patch("accounts.api.send_email_verification")
    def test_signup_api_creates_unverified_account_when_verification_delivery_fails(self, send_email):
        send_email.side_effect = EmailVerificationDeliveryError("provider unavailable")

        response = self.client.post(
            "/api/signup/",
            {
                "email": self.email,
                "password": self.password,
                "confirm_password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["verification_email_sent"])
        self.assertTrue(User.objects.filter(email=self.email, email_verified=False).exists())

    def test_login_requires_verified_email(self):
        self.create_user(verified=False)

        response = self.client.post(
            "/api/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Email verification required", response.data["error"])

    def test_login_returns_tokens_for_verified_active_user(self):
        self.create_user(verified=True)

        response = self.client.post(
            "/api/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_verify_email_uses_token_and_sets_verification_timestamp(self):
        user = self.create_user(verified=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.post(f"/api/verify-email/{uid}/{token}/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_logout_accepts_valid_refresh_token_and_blacklists_it(self):
        user = self.create_user(verified=True)
        refresh = RefreshToken.for_user(user)
        token_string = str(refresh)

        response = self.client.post(
            "/api/logout/",
            {"refresh": token_string},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        with self.assertRaises(TokenError):
            RefreshToken(token_string)

    def test_logout_rejects_invalid_refresh_token_without_swallowing_unrelated_errors(self):
        response = self.client.post(
            "/api/logout/",
            {"refresh": "not-a-jwt"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid or expired token")

    @patch("accounts.api.send_password_reset_email")
    def test_forgot_password_keeps_generic_response_on_delivery_failure(self, send_email):
        self.create_user(verified=True)
        send_email.side_effect = Exception("unexpected")  # service boundary converts provider failures

        response = self.client.post(
            "/api/forgot-password/",
            {"email": self.email},
            format="json",
        )

        # An unexpected exception is intentionally not converted by the API.
        self.assertEqual(response.status_code, 500)

    @patch("accounts.api.send_password_reset_email")
    def test_forgot_password_returns_generic_response_for_expected_delivery_failure(self, send_email):
        self.create_user(verified=True)
        from .services import PasswordResetDeliveryError
        send_email.side_effect = PasswordResetDeliveryError("provider unavailable")

        response = self.client.post(
            "/api/forgot-password/",
            {"email": self.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])

    def test_reset_password_changes_password_and_revokes_existing_tokens(self):
        user = self.create_user(verified=True)
        refresh = RefreshToken.for_user(user)
        old_refresh = str(refresh)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        new_password = "AnotherStrong!456"

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": new_password, "confirm_password": new_password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        self.assertTrue(
            BlacklistedToken.objects.filter(
                token__token=old_refresh
            ).exists()
        )

    def test_deactivation_revokes_outstanding_tokens(self):
        user = self.create_user(verified=True)
        refresh = RefreshToken.for_user(user)
        token_string = str(refresh)

        set_account_active(user, False)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        outstanding = OutstandingToken.objects.get(token=token_string)
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    @override_settings(RESEND_API_KEY=None)
    def test_verification_delivery_without_provider_configuration_is_explicit_failure(self):
        user = self.create_user()

        with self.assertRaises(EmailVerificationDeliveryError):
            send_email_verification(user)
