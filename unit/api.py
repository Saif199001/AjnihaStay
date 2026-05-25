from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from .models import Unit
from .serializers import UnitSerializer, SubUnitSerializer
from .services import get_units, create_unit, create_subunit


# 🔥 GET UNITS
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unit_list_api(request):

    property_id = request.GET.get("property")

    units = get_units(request.user, property_id).select_related("property").prefetch_related("subunits")
    serializer = UnitSerializer(units, many=True)

    return Response({
        "massage" : "units fetched",
        "data": serializer.data
    })
    

# 🔥 CREATE UNIT
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unit_create_api(request):

    serializer = UnitSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    unit = create_unit(request.user, serializer.validated_data)

    return Response({
        "message": "Unit created",
        "data": UnitSerializer(unit).data
    })


# 🔥 CREATE SUBUNIT (BED)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subunit_create_api(request):

    serializer = SubUnitSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    subunit = create_subunit(
        request.user,
        serializer.validated_data
    )

    return Response({
        "message": "SubUnit created",
        "data": SubUnitSerializer(subunit).data
    })