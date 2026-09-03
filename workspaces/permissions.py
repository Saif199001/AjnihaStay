from rest_framework.permissions import BasePermission

from .context import get_workspace_for_request

ROLE_LEVELS = {
    "staff": 10,
    "manager": 20,
    "admin": 30,
    "owner": 40,
}


class WorkspacePermission(BasePermission):
    minimum_role = "staff"

    def has_permission(self, request, view):
        try:
            workspace, membership = get_workspace_for_request(request)
        except Exception:
            return False

        request.workspace = workspace
        request.workspace_membership = membership
        return ROLE_LEVELS.get(membership.role, -1) >= ROLE_LEVELS[self.minimum_role]


class WorkspaceStaffPermission(WorkspacePermission):
    minimum_role = "staff"


class WorkspaceManagerPermission(WorkspacePermission):
    minimum_role = "manager"


class WorkspaceAdminPermission(WorkspacePermission):
    minimum_role = "admin"


class WorkspaceOwnerPermission(WorkspacePermission):
    minimum_role = "owner"
