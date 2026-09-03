from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Membership
from .serializers import WorkspaceSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_list_api(request):
    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    ).select_related("workspace")

    workspaces = []
    for membership in memberships:
        workspace = membership.workspace
        workspace.current_membership = membership
        workspaces.append(workspace)

    return Response({"data": WorkspaceSerializer(workspaces, many=True).data})
