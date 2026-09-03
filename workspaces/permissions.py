from rest_framework.permissions import BasePermission

from .context import get_workspace_for_request


ROLE_RANK = {
    "staff": 10,
    "manager": 20,
    "admin": 30,
    "owner": 40,
}


class HasWorkspaceMembership(BasePermission):
    message = "Active workspace membership required."

    def has_permission(self, request, view):
        try:
            workspace, membership = get_workspace_for_request(request)
        except Exception:
            return False
        request.workspace = workspace
        request.workspace_membership = membership
        return True


class HasWorkspaceRole(HasWorkspaceMembership):
    minimum_role = "staff"

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return ROLE_RANK[request.workspace_membership.role] >= ROLE_RANK[self.minimum_role]
