from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from .models import Membership, Workspace

WORKSPACE_HEADER = "HTTP_X_WORKSPACE_ID"


def get_workspace_for_request(request):
    if not request.user or not request.user.is_authenticated:
        raise NotAuthenticated("Authentication required")

    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    ).select_related("workspace")

    workspace_id = request.META.get(WORKSPACE_HEADER)
    if workspace_id:
        try:
            membership = memberships.get(workspace_id=int(workspace_id))
        except (ValueError, Membership.DoesNotExist):
            raise PermissionDenied("You do not have access to this workspace")
        return membership.workspace, membership

    if memberships.count() == 1:
        membership = memberships.first()
        return membership.workspace, membership

    if not memberships.exists():
        raise PermissionDenied("You are not a member of any active workspace")

    raise ValidationError({"workspace": "X-Workspace-ID header is required when you have multiple workspaces"})


def require_workspace_member(request):
    return get_workspace_for_request(request)
