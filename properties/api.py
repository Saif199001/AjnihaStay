from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.context import get_workspace_for_request
from workspaces.permissions import WorkspaceManagerPermission
from .models import Property
from .serializers import PropertySerializer
from .services import create_property


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def property_list_api(request):
    try:
        workspace, _ = get_workspace_for_request(request)
    except Exception as exc:
        return Response({"error": str(exc)}, status=403)

    properties = Property.objects.filter(workspace=workspace, is_active=True).order_by("id")
    return Response({"data": PropertySerializer(properties, many=True).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def property_create_api(request):
    serializer = PropertySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        property_obj = create_property(
            request.user,
            request.workspace,
            serializer.validated_data,
            request.FILES,
        )
        return Response({
            "message": "Property created successfully",
            "data": PropertySerializer(property_obj).data,
        })
    except Exception as exc:
        return Response({"error": str(exc)}, status=400)
