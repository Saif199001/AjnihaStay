from django.db.models import Q
from rest_framework import serializers

from properties.models import Property
from properties.serializers import PropertySerializer
from tenant.models import Occupancy
from .models import Unit, SubUnit


class SubUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubUnit
        fields = "__all__"


class UnitPropertyField(serializers.PrimaryKeyRelatedField):
    def use_pk_only_optimization(self):
        return False

    def to_representation(self, value):
        return PropertySerializer(value).data


class UnitSerializer(serializers.ModelSerializer):
    occupied_count = serializers.SerializerMethodField()
    occupancy_status = serializers.SerializerMethodField()
    property = UnitPropertyField(queryset=Property.objects.all())
    subunits = SubUnitSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_occupied_count(self, obj):
        return Occupancy.objects.filter(
            Q(unit=obj) | Q(subunit__unit=obj),
            is_active=True,
        ).count()

    def get_occupancy_status(self, obj):
        occupied = self.get_occupied_count(obj)
        if occupied == 0:
            return "Vacant"
        if occupied >= obj.capacity:
            return "Full"
        return "Partial"

    def validate(self, data):
        capacity = data.get("capacity")
        if capacity is not None and capacity <= 0:
            raise serializers.ValidationError("Capacity must be greater than 0")
        return data
