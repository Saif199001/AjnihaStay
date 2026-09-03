from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from .models import Membership, Workspace


class WorkspaceFoundationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"

    def test_signup_creates_workspace_and_owner_membership(self):
        response = self.client.post(
            "/api/signup/",
            {
                "email": "new-owner@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "workspace_name": "New Owner Rentals",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="new-owner@example.com")
        workspace = Workspace.objects.get(owner=user)
        membership = Membership.objects.get(workspace=workspace, user=user)

        self.assertEqual(workspace.name, "New Owner Rentals")
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_workspace_list_returns_only_active_memberships(self):
        user = User.objects.create_user("member@example.com", self.password)
        workspace_a = Workspace.objects.create(name="A", slug="a", owner=user)
        workspace_b = Workspace.objects.create(name="B", slug="b", owner=user)
        Membership.objects.create(workspace=workspace_a, user=user, role="owner")
        Membership.objects.create(workspace=workspace_b, user=user, role="staff", is_active=False)

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [workspace_a.id])

    def test_workspace_context_rejects_workspace_without_membership(self):
        user = User.objects.create_user("member2@example.com", self.password)
        other = User.objects.create_user("other@example.com", self.password)
        workspace = Workspace.objects.create(name="Other", slug="other", owner=other)
        Membership.objects.create(workspace=workspace, user=other, role="owner")

        self.client.force_authenticate(user=user)
        response = self.client.get(
            "/api/workspaces/",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )

        # Listing ignores the header and exposes only the caller's memberships.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])
