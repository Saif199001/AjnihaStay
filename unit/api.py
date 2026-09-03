from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .serializers import SubUnitSerializer, UnitSerializer
from .services import create_subunit, create_unit, get_units


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def unit_list_api(request):
    property_id = request.GET.get("property")
    units = get_units(request.workspace, property_id).select_related("property").prefetch_related("subunits")
    return Response({"message": "units fetched", "data": UnitSerializer(units, many=True).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def unit_create_api(request):
    serializer = UnitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        unit = create_unit(request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"message": "Unit created", "data": UnitSerializer(unit).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def subunit_create_api(request):
    serializer = SubUnitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        subunit = create_subunit(request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"message": "SubUnit created", "data": SubUnitSerializer(subunit).data})
