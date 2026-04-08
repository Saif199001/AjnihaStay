from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes

from .models import Property
from .serializers import PropertySerializer
from .services import create_property


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def property_list_api(request):

    properties = Property.objects.filter(owner=request.user)
    serializer = PropertySerializer(properties, many=True)

    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def property_create_api(request):

    property = create_property(request.user, request.data, request.FILES)
    serializer = PropertySerializer(property)

    return Response(serializer.data)