from rest_framework import serializers
from .models import Unit, SubUnit


class UnitSerializer(serializers.ModelSerializer):

    class Meta:
        model = Unit
        fields = "__all__"


class SubUnitSerializer(serializers.ModelSerializer):

    class Meta:
        model = SubUnit
        fields = "__all__"