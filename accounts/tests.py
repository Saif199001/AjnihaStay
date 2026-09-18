from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User, UserProfile
from .serializers import UserSerializer
from .services import EmailVerificationDeliveryError, set_account_active
from workspaces.models import Membership, Workspace


class AuthenticationSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"
        self.user = User.objects.create_user("owner@example.com", self.password)

    def test_protected_invoice_endpoint_requires_authentication(self):
        response = self.client.get("/api/invoices/")
        self.assertEqual(response.status_code, 401)

    def test_login_rejects_inactive_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_login_rejects_unverified_email(self, allow_request_mock):
        self.user.email_verified = False
        self.user.email_verified_at = None
        self.user.save(update_fields=["email_verified", "email_verified_at"])

        response = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"error": "Email verification required"})

    @override_settings(RESEND_API_KEY="test-key", FRONTEND_URL="https://app.example.com")
    @patch("accounts.api.resend.Emails.send")
    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_signup_creates_unverified_account_and_sends_verification_email(
        self, allow_request_mock, send_mock
    ):
        response = self.client.post(
            "/api/signup/",
            {
                "email": "verify@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "workspace_name": "Verify Workspace",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="verify@example.com")
        self.assertFalse(user.email_verified)
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(response.data["email_verification_required"])
        self.assertTrue(response.data["verification_email_sent"])
        self.assertNotIn("tokens", response.data)
        send_mock.assert_called_once()
        self.assertIn("/verify-email/", send_mock.call_args.args[0]["html"])
        allow_request_mock.assert_called()

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_verify_email_allows_login(self, allow_request_mock):
        self.user.email_verified = False
        self.user.email_verified_at = None
        self.user.save(update_fields=["email_verified", "email_verified_at"])
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(f"/api/verify-email/{uid}/{token}/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(self.user.email_verified_at)

        login = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)
        self.assertIn("refresh", login.data)

    def test_invalid_email_verification_token_is_rejected(self):
        self.user.email_verified = False
        self.user.email_verified_at = None
        self.user.save(update_fields=["email_verified", "email_verified_at"])
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.post(
            f"/api/verify-email/{uid}/invalid-token/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid or expired verification link", str(response.data))

    @override_settings(RESEND_API_KEY="test-key")
    @patch("accounts.api.resend.Emails.send")
    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_resend_verification_uses_generic_response(self, allow_request_mock, send_mock):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])

        response = self.client.post(
            "/api/resend-verification/",
            {"email": self.user.email},
            format="json",
        )

        unknown = self.client.post(
            "/api/resend-verification/",
            {"email": "missing@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, unknown.data)
        send_mock.assert_called_once()
        allow_request_mock.assert_called()

    def test_user_admin_deactivation_uses_account_service(self):
        from django.contrib import admin

        refresh = RefreshToken.for_user(self.user)
        token_string = str(refresh)
        self.user.is_active = False

        user_admin = admin.site._registry[User]
        user_admin.save_model(None, self.user, None, True)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__token=token_string).exists()
        )

    def test_account_deactivation_revokes_outstanding_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        token_string = str(refresh)

        updated = set_account_active(self.user, False)

        self.assertFalse(updated.is_active)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__token=token_string).exists()
        )

        login = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login.status_code, 401)

    @patch(
        "rest_framework_simplejwt.token_blacklist.models.BlacklistedToken.objects.get_or_create",
        side_effect=RuntimeError("blacklist unavailable"),
    )
    def test_account_deactivation_rolls_back_on_token_revocation_failure(self, blacklist_mock):
        RefreshToken.for_user(self.user)

        with self.assertRaises(RuntimeError):
            set_account_active(self.user, False)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        blacklist_mock.assert_called_once()

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

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_password_reset_revokes_all_outstanding_refresh_tokens(self, allow_request_mock):
        refresh_one = RefreshToken.for_user(self.user)
        refresh_two = RefreshToken.for_user(self.user)
        refresh_one_token = str(refresh_one)
        refresh_two_token = str(refresh_two)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": "NewStrongPass123!", "confirm_password": "NewStrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__token=refresh_one_token).exists()
        )
        self.assertTrue(
            BlacklistedToken.objects.filter(token__token=refresh_two_token).exists()
        )

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    @patch(
        "rest_framework_simplejwt.token_blacklist.models.BlacklistedToken.objects.get_or_create",
        side_effect=RuntimeError("blacklist unavailable"),
    )
    def test_password_reset_rolls_back_password_when_token_revocation_fails(
        self, blacklist_mock, allow_request_mock
    ):
        RefreshToken.for_user(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            f"/api/reset-password/{uid}/{token}/",
            {"password": "NewStrongPass123!", "confirm_password": "NewStrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"error": "Unable to complete password reset"})
        blacklist_mock.assert_called_once()

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertFalse(self.user.check_password("NewStrongPass123!"))

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_signup_uses_membership_role_as_canonical_role(self, allow_request_mock):
        response = self.client.post(
            "/api/signup/",
            {
                "email": "canonical-role@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "workspace_name": "Canonical Role Workspace",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="canonical-role@example.com")
        workspace = Workspace.objects.get(owner=user)
        membership = Membership.objects.get(workspace=workspace, user=user)

        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertNotIn("role", response.data["user"])
        self.assertFalse(hasattr(user, "role"))
        self.assertFalse(user.email_verified)
        self.assertNotIn("tokens", response.data)
        allow_request_mock.assert_called()

    def test_user_creation_creates_user_profile(self):
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_signup_uses_next_available_workspace_slug(self, allow_request_mock):
        existing_owner = User.objects.create_user(
            "collision-owner@example.com",
            self.password,
        )
        Workspace.objects.create(
            name="Existing Workspace",
            slug="collision",
            owner=existing_owner,
        )
        Membership.objects.create(
            workspace=Workspace.objects.get(slug="collision"),
            user=existing_owner,
            role=Membership.ROLE_OWNER,
            is_active=True,
        )

        response = self.client.post(
            "/api/signup/",
            {
                "email": "collision@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "workspace_name": "Collision Workspace",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        workspace = Workspace.objects.get(owner__email="collision@example.com")
        self.assertEqual(workspace.slug, "collision-2")
        self.assertTrue(UserProfile.objects.filter(user=workspace.owner).exists())

    def test_user_serializer_does_not_expose_role(self):
        data = UserSerializer(self.user).data

        self.assertEqual(set(data.keys()), {"id", "email"})
        self.assertNotIn("role", data)


    @patch("accounts.api.get_tokens_for_user")
    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_login_uses_canonical_token_issuer(self, allow_request_mock, token_mock):
        token_mock.return_value = {"access": "access-token", "refresh": "refresh-token"}
        response = self.client.post(
            "/api/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"], "access-token")
        self.assertEqual(response.data["refresh"], "refresh-token")
        token_mock.assert_called_once_with(self.user)

    @override_settings(RESEND_API_KEY="test-key")
    @patch("accounts.api.resend.Emails.send", side_effect=RuntimeError("provider down"))
    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_resend_verification_provider_failure_keeps_generic_response(self, allow_request_mock, send_mock):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])

        existing = self.client.post(
            "/api/resend-verification/",
            {"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            "/api/resend-verification/",
            {"email": "missing@example.com"},
            format="json",
        )

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(existing.data, unknown.data)
        send_mock.assert_called_once()
        allow_request_mock.assert_called()

    @override_settings(RESEND_API_KEY="test-key")
    @patch("accounts.api.resend.Emails.send", side_effect=RuntimeError("provider down"))
    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_signup_provider_failure_creates_unverified_account_without_tokens(
        self, allow_request_mock, send_mock
    ):
        response = self.client.post(
            "/api/signup/",
            {
                "email": "provider-failure@example.com",
                "password": self.password,
                "confirm_password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="provider-failure@example.com")
        self.assertFalse(user.email_verified)
        self.assertFalse(response.data["verification_email_sent"])
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        send_mock.assert_called_once()

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_signup_duplicate_email_returns_conflict_as_validation_error(
        self, allow_request_mock
    ):
        response = self.client.post(
            "/api/signup/",
            {
                "email": self.user.email.upper(),
                "password": self.password,
                "confirm_password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": ["Email already exists"]})

    def test_user_manager_canonicalizes_email(self):
        user = User.objects.create_user("MixedCase@Example.COM", self.password)
        self.assertEqual(user.email, "mixedcase@example.com")

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_password_reset_invalidates_same_reset_token_after_success(
        self, allow_request_mock
    ):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        payload = {
            "password": "NewStrongPass123!",
            "confirm_password": "NewStrongPass123!",
        }

        first = self.client.post(
            f"/api/reset-password/{uid}/{token}/", payload, format="json"
        )
        second = self.client.post(
            f"/api/reset-password/{uid}/{token}/", payload, format="json"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn("Invalid or expired token", str(second.data))


class AccountBoundaryHardeningTests(TestCase):
    def test_create_user_defaults_to_unverified(self):
        user = User.objects.create_user("boundary@example.com", "StrongPass123!")
        self.assertFalse(user.email_verified)
        self.assertIsNone(user.email_verified_at)

    def test_create_superuser_is_verified(self):
        user = User.objects.create_superuser("admin@example.com", "StrongPass123!")
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_create_superuser_forces_verification_state(self):
        user = User.objects.create_superuser(
            "forced-admin@example.com",
            "StrongPass123!",
            email_verified=False,
            email_verified_at=None,
        )
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_user_admin_cannot_edit_email_verification_state_directly(self):
        from django.contrib import admin
        user_admin = admin.site._registry[User]
        self.assertIn("email_verified", user_admin.readonly_fields)
        self.assertIn("email_verified_at", user_admin.readonly_fields)

    def test_verification_delivery_failure_is_classified(self):
        user = User.objects.create_user("delivery@example.com", "StrongPass123!")
        with patch(
            "accounts.services.resend.Emails.send",
            side_effect=RuntimeError("provider down"),
        ):
            from .services import send_email_verification

            with self.assertRaises(EmailVerificationDeliveryError):
                send_email_verification(user)


    @override_settings(RESEND_API_KEY="test-key")
    @patch("accounts.services.default_token_generator.make_token", side_effect=RuntimeError("unexpected token failure"))
    def test_verification_token_generation_failure_is_not_classified_as_delivery_failure(
        self, token_mock
    ):
        user = User.objects.create_user("boundary-token@example.com", "StrongPass123!")

        from .services import send_email_verification

        with self.assertRaises(RuntimeError):
            send_email_verification(user)

        token_mock.assert_called_once_with(user)

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_email_endpoints_reject_non_string_email_input(self, allow_request_mock):
        for path, payload in (
            ("/api/login/", {"email": 123, "password": "StrongPass123!"}),
            ("/api/resend-verification/", {"email": 123}),
            ("/api/forgot-password/", {"email": 123}),
            (
                "/api/signup/",
                {
                    "email": 123,
                    "password": "StrongPass123!",
                    "confirm_password": "StrongPass123!",
                },
            ),
        ):
            response = self.client.post(path, payload, format="json")
            expected_status = 401 if path == "/api/login/" else 400
            self.assertEqual(response.status_code, expected_status, path)

        allow_request_mock.assert_called()
