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

    def test_password_reset_revokes_all_outstanding_refresh_tokens(self):
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

    @patch(
        "rest_framework_simplejwt.token_blacklist.models.BlacklistedToken.objects.get_or_create",
        side_effect=RuntimeError("blacklist unavailable"),
    )
    def test_password_reset_rolls_back_password_when_token_revocation_fails(self, blacklist_mock):
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
        allow_request_mock.assert_called()

    def test_user_creation_creates_user_profile(self):
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_signup_uses_next_available_workspace_slug(self):
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
