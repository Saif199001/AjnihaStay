from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.context import get_workspace_for_request
from .serializers import ChargeSerializer, OccupancySerializer, TenantSerializer
from .services import create_charge, create_occupancy, create_tenant, get_charges, get_tenants


def _workspace_or_error(request):
    try:
        return get_workspace_for_request(request)
    except Exception as exc:
        return None, Response({"error": str(exc)}, status=403)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tenant_create_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    serializer = TenantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        tenant = create_tenant(request.user, workspace, serializer.validated_data, request.FILES)
        return Response({"message": "Tenant created", "data": TenantSerializer(tenant).data})
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_list_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    return Response({"data": TenantSerializer(get_tenants(workspace), many=True).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def occupancy_create_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    serializer = OccupancySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        occupancy = create_occupancy(request.user, workspace, serializer.validated_data)
        return Response({"message": "Occupancy created", "data": OccupancySerializer(occupancy).data})
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def charge_create_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    serializer = ChargeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        charge = create_charge(request.user, workspace, serializer.validated_data)
        return Response({"message": "Charges Created", "data": ChargeSerializer(charge).data})
    except (ValidationError, Exception) as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def charge_list_api(request):
    workspace, error = _workspace_or_error(request)
    if error:
        return error
    occupancy_id = request.GET.get("occupancy")
    charges = get_charges(occupancy_id, workspace)
    return Response(ChargeSerializer(charges, many=True).data)
