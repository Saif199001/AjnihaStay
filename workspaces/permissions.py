from rest_framework.permissions import BasePermission

from .context import get_workspace_for_request
from .db import set_workspace_context
from .models import Membership


ROLE_RANK = {
    Membership.ROLE_VIEWER: 10,
    Membership.ROLE_MANAGER: 20,
    Membership.ROLE_ADMIN: 30,
    Membership.ROLE_OWNER: 40,
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
        try:
            set_workspace_context(workspace.id)
        except Exception:
            return False
        return True


class HasWorkspaceRole(HasWorkspaceMembership):
    minimum_role = Membership.ROLE_VIEWER

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        member_rank = ROLE_RANK.get(request.workspace_membership.role, 0)
        minimum_rank = ROLE_RANK.get(self.minimum_role, 0)
        return member_rank >= minimum_rank


class WorkspaceViewerPermission(HasWorkspaceRole):
    minimum_role = Membership.ROLE_VIEWER


class WorkspaceManagerPermission(HasWorkspaceRole):
    minimum_role = Membership.ROLE_MANAGER


class WorkspaceAdminPermission(HasWorkspaceRole):
    minimum_role = Membership.ROLE_ADMIN


class WorkspaceOwnerPermission(HasWorkspaceRole):
    minimum_role = Membership.ROLE_OWNER
