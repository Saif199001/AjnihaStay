from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Membership, Workspace, _allow_membership_mutation

User = get_user_model()


class WorkspaceApiErrorContractProductionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"

    def create_user(self, email):
        return User.objects.create_user(
            email=email,
            password=self.password,
            email_verified=True,
            is_active=True,
        )

    def create_owned_workspace(self, owner, slug):
        workspace = Workspace.objects.create(
            name="Test Workspace",
            slug=slug,
            owner=owner,
        )
        with _allow_membership_mutation():
            Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=Membership.ROLE_OWNER,
                is_active=True,
            )
        return workspace

    def create_membership(
        self,
        workspace,
        user,
        role=Membership.ROLE_VIEWER,
        is_active=True,
    ):
        with _allow_membership_mutation():
            return Membership.objects.create(
                workspace=workspace,
                user=user,
                role=role,
                is_active=is_active,
            )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def workspace_headers(self, workspace):
        return {"HTTP_X_WORKSPACE_ID": str(workspace.id)}

    def test_unauthenticated_workspace_current_returns_401(self):
        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 401)

    def test_authenticated_non_member_returns_403(self):
        user = self.create_user("outsider@example.com")
        self.authenticate(user)

        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "You are not a member of any active workspace",
        )

    def test_multiple_workspaces_without_selection_returns_400(self):
        user = self.create_user("multi@example.com")
        self.create_owned_workspace(user, "multi-one")
        self.create_owned_workspace(user, "multi-two")
        self.authenticate(user)

        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["workspace"][0],
            "X-Workspace-ID header is required when you have multiple workspaces",
        )

    def test_inaccessible_workspace_selection_returns_403(self):
        owner = self.create_user("owner@example.com")
        outsider = self.create_user("outsider@example.com")
        workspace = self.create_owned_workspace(owner, "private-workspace")
        self.authenticate(outsider)

        response = self.client.get(
            "/api/workspaces/current/",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "You do not have access to this workspace",
        )

    def test_workspace_update_validation_error_returns_400(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "update-validation")
        self.authenticate(owner)

        response = self.client.patch(
            "/api/workspaces/current/",
            {"name": "   "},
            format="json",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_workspace_update_unauthorized_member_returns_403(self):
        owner = self.create_user("owner@example.com")
        viewer = self.create_user("viewer@example.com")
        workspace = self.create_owned_workspace(owner, "update-permission")
        self.create_membership(workspace, viewer, Membership.ROLE_VIEWER)
        self.authenticate(viewer)

        response = self.client.patch(
            "/api/workspaces/current/",
            {"name": "Changed Name"},
            format="json",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "Workspace admin permission required",
        )

    def test_transfer_ownership_unauthorized_member_returns_403(self):
        owner = self.create_user("owner@example.com")
        viewer = self.create_user("viewer@example.com")
        target = self.create_user("target@example.com")
        workspace = self.create_owned_workspace(owner, "transfer-permission")
        self.create_membership(workspace, viewer, Membership.ROLE_VIEWER)
        self.create_membership(workspace, target, Membership.ROLE_VIEWER)
        self.authenticate(viewer)

        response = self.client.post(
            "/api/workspaces/current/transfer-ownership/",
            {"target_user_id": target.id},
            format="json",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "Workspace owner permission required",
        )

    def test_transfer_invalid_target_returns_400(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "transfer-validation")
        self.authenticate(owner)

        response = self.client.post(
            "/api/workspaces/current/transfer-ownership/",
            {"target_user_id": 999999999},
            format="json",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Target user must be an active workspace member",
        )

    def test_archive_unauthorized_member_returns_403(self):
        owner = self.create_user("archive-owner@example.com")
        viewer = self.create_user("archive-viewer@example.com")
        workspace = self.create_owned_workspace(owner, "archive-permission")
        self.create_membership(workspace, viewer, Membership.ROLE_VIEWER)
        self.authenticate(viewer)

        response = self.client.post(
            "/api/workspaces/current/archive/",
            {},
            format="json",
            **self.workspace_headers(workspace),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "Workspace owner permission required",
        )

    def test_unexpected_service_error_propagates(self):
        owner = self.create_user("unexpected@example.com")
        workspace = self.create_owned_workspace(owner, "unexpected-error")
        self.authenticate(owner)

        with patch(
            "workspaces.api.update_workspace",
            side_effect=RuntimeError("unexpected service failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected service failure",
            ):
                self.client.patch(
                    "/api/workspaces/current/",
                    {"name": "New Name"},
                    format="json",
                    **self.workspace_headers(workspace),
                )
