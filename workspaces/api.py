from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from .context import get_workspace_for_request
from .serializers import (
    WorkspaceSerializer,
    WorkspaceTransferOwnershipSerializer,
    WorkspaceUpdateSerializer,
)
from .services import archive_workspace, transfer_workspace_ownership, update_workspace


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_list_api(request):
    from .models import Membership

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


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def workspace_current_api(request):
    try:
        workspace, membership = get_workspace_for_request(request)
    except (NotAuthenticated, PermissionDenied, ValidationError) as exc:
        return Response({"error": str(exc)}, status=403)

    if request.method == "PATCH":
        serializer = WorkspaceUpdateSerializer(workspace, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            workspace = update_workspace(
                workspace,
                membership,
                serializer.validated_data["name"],
            )
        except ValidationError as exc:
            return Response({"error": str(exc)}, status=400)

    workspace.current_membership = membership
    return Response({"data": {"workspace": WorkspaceSerializer(workspace).data}})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_transfer_ownership_api(request):
    try:
        workspace, membership = get_workspace_for_request(request)
    except (NotAuthenticated, PermissionDenied, ValidationError) as exc:
        return Response({"error": str(exc)}, status=403)

    serializer = WorkspaceTransferOwnershipSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        workspace = transfer_workspace_ownership(
            workspace,
            membership,
            serializer.validated_data["target_user_id"],
        )
    except (NotAuthenticated, PermissionDenied, ValidationError) as exc:
        return Response({"error": str(exc)}, status=400)

    workspace.current_membership = workspace.memberships.get(user=request.user)
    return Response({"data": {"workspace": WorkspaceSerializer(workspace).data}})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_archive_api(request):
    try:
        workspace, membership = get_workspace_for_request(request)
    except (NotAuthenticated, PermissionDenied, ValidationError) as exc:
        return Response({"error": str(exc)}, status=403)

    try:
        workspace = archive_workspace(workspace, membership)
    except (NotAuthenticated, PermissionDenied, ValidationError) as exc:
        return Response({"error": str(exc)}, status=400)

    workspace.current_membership = membership
    return Response({"data": {"workspace": WorkspaceSerializer(workspace).data}})
