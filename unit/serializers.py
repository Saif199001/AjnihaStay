from rest_framework import serializers
from properties.serializers import PropertySerializer
from .models import Unit, SubUnit
from django.db.models import Q
from tenant.models import Occupancy


class SubUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubUnit
        fields = "__all__"


class UnitSerializer(serializers.ModelSerializer):

    occupied_count = serializers.SerializerMethodField()

    occupancy_status = serializers.SerializerMethodField()

    property = PropertySerializer(read_only=True)

    subunits = SubUnitSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = "__all__"

    def get_occupied_count(self, obj):

        return Occupancy.objects.filter(
            Q(unit=obj) |
            Q(subunit__unit=obj),
            is_active=True
        ).count()


    def get_occupancy_status(self, obj):

        occupied = self.get_occupied_count(obj)

        if occupied == 0:
            return "Vacant"

        if occupied >= obj.capacity:
            return "Full"

        return "Partial"

    def validate(self, data):
        if data.get("capacity", 1) <= 0:
            raise serializers.ValidationError("Capacity must be greater than 0")
        return data