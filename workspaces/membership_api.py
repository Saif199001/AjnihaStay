from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import WorkspaceAdminPermission
from .serializers import (
    MembershipCreateSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
)
from .services import add_member, change_member_role, deactivate_member, list_members


@api_view(["GET", "POST"])
@permission_classes([WorkspaceAdminPermission])
def workspace_members_api(request):
    if request.method == "GET":
        return Response({"data": MembershipSerializer(list_members(request.workspace), many=True).data})

    serializer = MembershipCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        membership = add_member(
            request.workspace,
            request.workspace_membership,
            serializer.validated_data["email"],
            serializer.validated_data["role"],
        )
    except Exception as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"data": MembershipSerializer(membership).data}, status=201)


@api_view(["PATCH"])
@permission_classes([WorkspaceAdminPermission])
def workspace_member_role_api(request, user_id):
    serializer = MembershipRoleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        membership = change_member_role(
            request.workspace,
            request.workspace_membership,
            user_id,
            serializer.validated_data["role"],
        )
    except Exception as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"data": MembershipSerializer(membership).data})


@api_view(["DELETE"])
@permission_classes([WorkspaceAdminPermission])
def workspace_member_deactivate_api(request, user_id):
    try:
        membership = deactivate_member(
            request.workspace,
            request.workspace_membership,
            user_id,
        )
    except Exception as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"data": MembershipSerializer(membership).data})
