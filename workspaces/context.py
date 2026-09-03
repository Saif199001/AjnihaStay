from django.core.exceptions import PermissionDenied

from .models import Membership

WORKSPACE_HEADER = "HTTP_X_WORKSPACE_ID"


def get_workspace_for_request(request):
    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("Authentication required")

    workspace_id = request.META.get(WORKSPACE_HEADER)
    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    ).select_related("workspace")

    if workspace_id:
        try:
            membership = memberships.get(workspace_id=workspace_id)
        except Membership.DoesNotExist:
            raise PermissionDenied("You do not have access to this workspace")
        return membership.workspace, membership

    if memberships.count() == 1:
        membership = memberships.first()
        return membership.workspace, membership

    raise PermissionDenied("Workspace selection is required")
