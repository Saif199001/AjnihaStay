from rest_framework import serializers
from .models import Unit, SubUnit


class SubUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubUnit
        fields = "__all__"


class UnitSerializer(serializers.ModelSerializer):

    subunits = SubUnitSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = "__all__"

    def validate(self, data):
        if data.get("capacity", 1) <= 0:
            raise serializers.ValidationError("Capacity must be greater than 0")
        return data