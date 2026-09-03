from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.context import get_workspace_for_request
from .serializers import SubUnitSerializer, UnitSerializer
from .services import create_subunit, create_unit, get_units


def _workspace_or_error(request):
    try:
        return get_workspace_for_request(request)
    except Exception as exc:
        return None, Response({"error": str(exc)}, status=403)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unit_list_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    property_id = request.GET.get("property")
    units = get_units(workspace, property_id).select_related("property").prefetch_related("subunits")
    return Response({"message": "units fetched", "data": UnitSerializer(units, many=True).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unit_create_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    serializer = UnitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        unit = create_unit(workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"message": "Unit created", "data": UnitSerializer(unit).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subunit_create_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    serializer = SubUnitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        subunit = create_subunit(workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"message": "SubUnit created", "data": SubUnitSerializer(subunit).data})
