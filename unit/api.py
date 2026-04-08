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

    units = get_units(request.user, property_id)
    serializer = UnitSerializer(units, many=True)

    return Response(serializer.data)


# 🔥 CREATE UNIT
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unit_create_api(request):

    unit = create_unit(request.user, request.data)
    serializer = UnitSerializer(unit)

    return Response(serializer.data)


# 🔥 CREATE SUBUNIT (BED)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subunit_create_api(request):

    try:
        subunit = create_subunit(request.user, request.data)
        serializer = SubUnitSerializer(subunit)
        return Response(serializer.data)

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)