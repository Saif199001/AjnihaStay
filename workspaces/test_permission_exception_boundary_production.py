from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory

from .permissions import (
    WorkspaceAdminPermission,
    WorkspaceOwnerPermission,
    WorkspaceViewerPermission,
)


class WorkspacePermissionExceptionBoundaryProductionTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def make_request(self):
        return self.factory.get("/")

    def test_expected_not_authenticated_exception_propagates(self):
        request = self.make_request()

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            side_effect=NotAuthenticated("Authentication required"),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            with self.assertRaises(NotAuthenticated):
                WorkspaceViewerPermission().has_permission(request, None)

        set_context.assert_not_called()

    def test_expected_permission_denied_exception_propagates(self):
        request = self.make_request()

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            side_effect=PermissionDenied("Workspace access denied"),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            with self.assertRaises(PermissionDenied):
                WorkspaceViewerPermission().has_permission(request, None)

        set_context.assert_not_called()

    def test_expected_validation_error_propagates(self):
        request = self.make_request()

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            side_effect=ValidationError(
                {"workspace": "X-Workspace-ID header is required"}
            ),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            with self.assertRaises(ValidationError):
                WorkspaceViewerPermission().has_permission(request, None)

        set_context.assert_not_called()

    def test_unexpected_workspace_resolution_exception_propagates(self):
        request = self.make_request()

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            side_effect=RuntimeError("unexpected workspace resolution failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected workspace resolution failure",
            ):
                WorkspaceViewerPermission().has_permission(request, None)

    def test_successful_workspace_resolution_sets_request_context(self):
        request = self.make_request()
        workspace = SimpleNamespace(id=123)
        membership = SimpleNamespace(role="viewer")

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            return_value=(workspace, membership),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            allowed = WorkspaceViewerPermission().has_permission(request, None)

        self.assertTrue(allowed)
        self.assertIs(request.workspace, workspace)
        self.assertIs(request.workspace_membership, membership)
        set_context.assert_called_once_with(123)

    def test_unexpected_workspace_context_exception_propagates(self):
        request = self.make_request()
        workspace = SimpleNamespace(id=123)
        membership = SimpleNamespace(role="viewer")

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            return_value=(workspace, membership),
        ), patch(
            "workspaces.permissions.set_workspace_context",
            side_effect=RuntimeError("unexpected database context failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected database context failure",
            ):
                WorkspaceViewerPermission().has_permission(request, None)

    def test_admin_permission_keeps_role_boundary(self):
        request = self.make_request()
        workspace = SimpleNamespace(id=123)
        viewer_membership = SimpleNamespace(role="viewer")

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            return_value=(workspace, viewer_membership),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            allowed = WorkspaceAdminPermission().has_permission(request, None)

        self.assertFalse(allowed)
        set_context.assert_called_once_with(123)

    def test_owner_permission_allows_owner_role(self):
        request = self.make_request()
        workspace = SimpleNamespace(id=123)
        owner_membership = SimpleNamespace(role="owner")

        with patch(
            "workspaces.permissions.get_workspace_for_request",
            return_value=(workspace, owner_membership),
        ), patch("workspaces.permissions.set_workspace_context") as set_context:
            allowed = WorkspaceOwnerPermission().has_permission(request, None)

        self.assertTrue(allowed)
        set_context.assert_called_once_with(123)
