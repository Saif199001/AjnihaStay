from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from workspaces.models import Membership, Workspace

from .services import (
    EmailVerificationDeliveryError,
    PasswordResetDeliveryError,
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

    def create_user(self, *, email=None, verified=False, active=True):
        user = User.objects.create_user(
            email=email or self.email,
            password=self.password,
            email_verified=verified,
            is_active=active,
        )
        if verified:
            user.email_verified_at = user.date_joined
            user.save(update_fields=["email_verified_at"])
        return user

    def verification_link(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token

    def test_user_manager_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user(
            email="  OWNER@Example.COM ",
            password=self.password,
        )
        self.assertEqual(user.email, "owner@example.com")
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.email_verified)
        self.assertIsNotNone(user.date_joined)

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
        self.assertEqual(workspace.name, "Owner Workspace")
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_create_user_account_uses_default_workspace_name(self):
        user = create_user_account(
            self.email,
            self.password,
            self.password,
        )
        workspace = Workspace.objects.get(owner=user)
        self.assertEqual(workspace.name, "owner@example.com's Workspace")

    def test_create_user_account_rejects_password_mismatch(self):
        with self.assertRaisesMessage(ValidationError, "Passwords do not match"):
            create_user_account(
                self.email,
                self.password,
                "DifferentPassword!123",
            )

    def test_create_user_account_rejects_duplicate_email(self):
        self.create_user()
        with self.assertRaisesMessage(ValidationError, "Email already exists"):
            create_user_account(self.email, self.password, self.password)

    def test_create_user_account_rejects_weak_password(self):
        with self.assertRaises(ValidationError):
            create_user_account(self.email, "123", "123")

    @patch("accounts.api.send_email_verification")
    def test_signup_creates_account_when_verification_delivery_fails(self, send_email):
        send_email.side_effect = EmailVerificationDeliveryError("provider unavailable")

        response = self.client.post(
            "/api/signup/",
            {
                "email": "  OWNER@Example.COM ",
                "password": self.password,
                "confirm_password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["verification_email_sent"])
        self.assertTrue(
            User.objects.filter(
                email=self.email,
                email_verified=False,
            ).exists()
        )

    def test_signup_rejects_missing_required_fields(self):
        response = self.client.post(
            "/api/signup/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_login_rejects_missing_credentials(self):
        response = self.client.post("/api/login/", {"email": self.email}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_login_rejects_invalid_credentials(self):
        self.create_user(verified=True)
        response = self.client.post(
            "/api/login/",
            {"email": self.email, "password": "WrongPassword!999"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_login_requires_verified_email(self):
        self.create_user(verified=False)
        response = self.client.post(
            "/api/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Email verification required", response.data["error"])

    def test_login_rejects_inactive_account(self):
        self.create_user(verified=True, active=False)
        response = self.client.post(
            "/api/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_login_returns_tokens_for_verified_active_user(self):
        self.create_user(verified=True)
        response = self.client.post(
            "/api/login/",
            {"email": "  OWNER@Example.COM ", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_verify_email_accepts_valid_token(self):
        user = self.create_user()
        uid, token = self.verification_link(user)

        response = self.client.post(
            f"/api/verify-email/{uid}/{token}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_verify_email_rejects_invalid_token(self):
        user = self.create_user()
        uid, _ = self.verification_link(user)

        response = self.client.post(
            f"/api/verify-email/{uid}/invalid-token/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_verify_email_is_idempotent_for_verified_account(self):
        user = self.create_user(verified=True)
        uid, token = self.verification_link(user)

        response = self.client.post(
            f"/api/verify-email/{uid}/{token}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Email already verified")

    @patch("accounts.api.send_email_verification")
    def test_resend_verification_returns_generic_response_for_existing_unverified_user(self, send_email):
        self.create_user()
        response = self.client.post(
            "/api/resend-verification/",
            {"email": "  OWNER@Example.COM "},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        send_email.assert_called_once()

    def test_resend_verification_returns_generic_response_for_unknown_email(self):
        response = self.client.post(
            "/api/resend-verification/",
            {"email": "unknown@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])

    @patch("accounts.api.send_email_verification")
    def test_resend_verification_hides_delivery_failure(self, send_email):
        self.create_user()
        send_email.side_effect = EmailVerificationDeliveryError("provider unavailable")

        response = self.client.post(
            "/api/resend-verification/",
            {"email": self.email},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])

    def test_resend_verification_rejects_missing_email(self):
        response = self.client.post("/api/resend-verification/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_logout_blacklists_valid_refresh_token(self):
        user = self.create_user(verified=True)
        token_string = str(RefreshToken.for_user(user))

        response = self.client.post(
            "/api/logout/",
            {"refresh": token_string},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        with self.assertRaises(TokenError):
            RefreshToken(token_string)

    def test_logout_rejects_invalid_refresh_token(self):
        response = self.client.post(
            "/api/logout/",
            {"refresh": "not-a-jwt"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid or expired token")

    def test_logout_rejects_missing_refresh_token(self):
        response = self.client.post("/api/logout/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("accounts.api.send_password_reset_email")
    def test_forgot_password_returns_generic_response_for_existing_user(self, send_email):
        self.create_user(verified=True)

        response = self.client.post(
            "/api/forgot-password/",
            {"email": "  OWNER@Example.COM "},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])
        send_email.assert_called_once()

    def test_forgot_password_returns_generic_response_for_unknown_email(self):
        response = self.client.post(
            "/api/forgot-password/",
            {"email": "unknown@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])

    @patch("accounts.api.send_password_reset_email")
    def test_forgot_password_hides_expected_delivery_failure(self, send_email):
        self.create_user(verified=True)
        send_email.side_effect = PasswordResetDeliveryError("provider unavailable")

        response = self.client.post(
            "/api/forgot-password/",
            {"email": self.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("If the account exists", response.data["message"])

    @patch("accounts.api.send_password_reset_email")
    def test_forgot_password_does_not_swallow_unexpected_errors(self, send_email):
        self.create_user(verified=True)
        send_email.side_effect = RuntimeError("unexpected programming failure")

        with self.assertRaises(RuntimeError):
            self.client.post(
                "/api/forgot-password/",
                {"email": self.email},
                format="json",
            )

    def test_reset_password_changes_password_and_revokes_existing_tokens(self):
        user = self.create_user(verified=True)
        old_refresh = str(RefreshToken.for_user(user))
        uid, token = self.verification_link(user)
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

    def test_reset_password_rejects_mismatched_passwords(self):
        user = self.create_user(verified=True)
        uid, token = self.verification_link(user)

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": "AnotherStrong!456", "confirm_password": "Different!789"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_reset_password_rejects_invalid_token(self):
        user = self.create_user(verified=True)
        uid, _ = self.verification_link(user)

        response = self.client.post(
            f"/api/reset-password/{uid}/invalid-token/",
            {"password": "AnotherStrong!456", "confirm_password": "AnotherStrong!456"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_reset_password_rejects_weak_password(self):
        user = self.create_user(verified=True)
        uid, token = self.verification_link(user)

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": "123", "confirm_password": "123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_deactivation_revokes_outstanding_tokens(self):
        user = self.create_user(verified=True)
        token_string = str(RefreshToken.for_user(user))

        updated_user = set_account_active(user, False)

        self.assertFalse(updated_user.is_active)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        outstanding = OutstandingToken.objects.get(token=token_string)
        self.assertTrue(
            BlacklistedToken.objects.filter(token=outstanding).exists()
        )

    def test_reactivation_restores_account_without_creating_new_tokens(self):
        user = self.create_user(verified=True, active=False)
        updated_user = set_account_active(user, True)

        self.assertTrue(updated_user.is_active)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    @override_settings(RESEND_API_KEY=None)
    def test_verification_delivery_without_provider_configuration_is_explicit_failure(self):
        user = self.create_user()
        with self.assertRaises(EmailVerificationDeliveryError):
            send_email_verification(user)

    @override_settings(RESEND_API_KEY=None)
    def test_password_reset_delivery_without_provider_configuration_is_explicit_failure(self):
        from .services import send_password_reset_email

        user = self.create_user()
        with self.assertRaises(PasswordResetDeliveryError):
            send_password_reset_email(user)
