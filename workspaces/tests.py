from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from .models import Membership, Workspace
from .context import get_workspace_for_request


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
            "/api/workspaces/current/",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )

        self.assertEqual(response.status_code, 403)

    def test_single_membership_is_selected_without_header(self):
        user = User.objects.create_user("single@example.com", self.password)
        workspace = Workspace.objects.create(name="Single", slug="single", owner=user)
        Membership.objects.create(workspace=workspace, user=user, role="owner")

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["workspace"]["id"], workspace.id)

    def test_multiple_memberships_require_explicit_workspace(self):
        user = User.objects.create_user("multi@example.com", self.password)
        workspace_a = Workspace.objects.create(name="A", slug="multi-a", owner=user)
        workspace_b = Workspace.objects.create(name="B", slug="multi-b", owner=user)
        Membership.objects.create(workspace=workspace_a, user=user, role="owner")
        Membership.objects.create(workspace=workspace_b, user=user, role="admin")

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 403)

    def test_workspace_context_returns_only_callers_membership(self):
        user = User.objects.create_user("context@example.com", self.password)
        workspace = Workspace.objects.create(name="Mine", slug="mine", owner=user)
        Membership.objects.create(workspace=workspace, user=user, role="manager")

        other = User.objects.create_user("intruder@example.com", self.password)
        other_workspace = Workspace.objects.create(name="Other", slug="other-context", owner=other)
        Membership.objects.create(workspace=other_workspace, user=other, role="owner")

        self.client.force_authenticate(user=user)
        request = self.client.get(
            "/api/workspaces/current/",
            HTTP_X_WORKSPACE_ID=str(other_workspace.id),
        ).wsgi_request

        with self.assertRaises(Exception):
            get_workspace_for_request(request)

    def test_property_is_scoped_to_workspace(self):
        owner = User.objects.create_user("property-owner@example.com", self.password)
        other = User.objects.create_user("property-other@example.com", self.password)
        workspace = Workspace.objects.create(name="Owner WS", slug="property-owner", owner=owner)
        other_workspace = Workspace.objects.create(name="Other WS", slug="property-other", owner=other)
        Membership.objects.create(workspace=workspace, user=owner, role="owner")
        Membership.objects.create(workspace=other_workspace, user=other, role="owner")
        prop = Property.objects.create(
            owner=owner,
            workspace=workspace,
            name="Owner Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )

        self.assertEqual(Property.objects.filter(workspace=workspace).count(), 1)
        self.assertEqual(Property.objects.filter(workspace=other_workspace).count(), 0)
        self.assertEqual(prop.workspace_id, workspace.id)
