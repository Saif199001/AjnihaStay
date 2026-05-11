from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from .services import create_tenant, get_tenants, create_occupancy, create_charge, get_charges
from .serializers import TenantSerializer, OccupancySerializer, ChargeSerializer

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tenant_create_api(request):

    serializer = TenantSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        tenant = create_tenant(
            request.user,
            serializer.validated_data,
            request.FILES   # 🔥 FILE SUPPORT
        )

        return Response({
            "message": "Tenant created",
            "data": TenantSerializer(tenant).data
        })

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_list_api(request):

    tenants = get_tenants(request.user)
    serializer = TenantSerializer(tenants, many=True)

    return Response({"data": serializer.data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def occupancy_create_api(request):

    serializer = OccupancySerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        
        occupancy = create_occupancy(
        request.user,
        serializer.validated_data
        )

        return Response({
            "message": "Occupancy created",
            "data": OccupancySerializer(occupancy).data
        })

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def charge_create_api(request):

    serializer = ChargeSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        charge = create_charge(
            request.user,
            serializer.validated_data
        )

        return Response({
            "message": "Charges Created",
            "data": ChargeSerializer(charge).data
        })

    except Exception as e:
        return Response({"error": str(e)}, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def charge_list_api(request):

    occupancy_id = request.GET.get("occupancy")

    charges = get_charges(occupancy_id, request.user)
    serializer = ChargeSerializer(charges, many=True)

    return Response(serializer.data)