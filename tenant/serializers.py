from rest_framework import serializers
from .models import Tenant, Occupancy, Charge


class TenantSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tenant
        fields = "__all__"


class OccupancySerializer(serializers.ModelSerializer):

    class Meta:
        model = Occupancy
        fields = "__all__"

class ChargeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Charge
        fields = "__all__"