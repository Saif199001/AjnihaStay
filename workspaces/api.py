from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .context import get_workspace_for_request
from .models import Membership
from .serializers import MembershipSerializer, WorkspaceSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_list_api(request):
    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    ).select_related("workspace")
    workspaces = [membership.workspace for membership in memberships]
    return Response({"data": WorkspaceSerializer(workspaces, many=True, context={"request": request}).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_current_api(request):
    workspace, membership = get_workspace_for_request(request)
    return Response({
        "data": {
            "workspace": WorkspaceSerializer(workspace, context={"request": request}).data,
            "membership": MembershipSerializer(membership).data,
        }
    })
