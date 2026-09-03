from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .serializers import ChargeSerializer, OccupancySerializer, TenantSerializer
from .services import create_charge, create_occupancy, create_tenant, get_charges, get_tenants


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def tenant_create_api(request):
    serializer = TenantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        tenant = create_tenant(request.user, request.workspace, serializer.validated_data, request.FILES)
        return Response({"message": "Tenant created", "data": TenantSerializer(tenant).data})
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def tenant_list_api(request):
    return Response({"data": TenantSerializer(get_tenants(request.workspace), many=True).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def occupancy_create_api(request):
    serializer = OccupancySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        occupancy = create_occupancy(request.user, request.workspace, serializer.validated_data)
        return Response({"message": "Occupancy created", "data": OccupancySerializer(occupancy).data})
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def charge_create_api(request):
    serializer = ChargeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        charge = create_charge(request.user, request.workspace, serializer.validated_data)
        return Response({"message": "Charges Created", "data": ChargeSerializer(charge).data})
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def charge_list_api(request):
    occupancy_id = request.GET.get("occupancy")
    charges = get_charges(occupancy_id, request.workspace)
    return Response(ChargeSerializer(charges, many=True).data)
