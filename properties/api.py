from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .models import Property
from .serializers import PropertySerializer
from .services import create_property


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def property_list_api(request):
    properties = Property.objects.filter(workspace=request.workspace, is_active=True).order_by("id")
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
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
