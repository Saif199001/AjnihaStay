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

    return Response({"data": serializer.data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def property_create_api(request):

    serializer = PropertySerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        property = create_property(
            request.user,
            serializer.validated_data,
            request.FILES
        )

        return Response({
            "message": "Property created successfully",
            "data": PropertySerializer(property).data
        })

    except Exception as e:
        return Response({"error": str(e)}, status=400)