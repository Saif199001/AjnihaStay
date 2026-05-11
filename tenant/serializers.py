from rest_framework import serializers
from .models import Tenant, Occupancy, Charge
from payments.serializers import InvoiceSerializer



class OccupancySerializer(serializers.ModelSerializer):

    invoices = InvoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Occupancy
        fields = "__all__"

    def validate(self, data):
        if data.get("rent") <= 0:
            raise serializers.ValidationError("Rent must be greater than 0")

        if data.get("check_in_date") > data.get("next_due_date"):
            raise serializers.ValidationError("Invalid dates")

        return data


class TenantSerializer(serializers.ModelSerializer):

    occupancies = OccupancySerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = "__all__"

    def validate_phone(self, value):
        if len(value) < 10:
            raise serializers.ValidationError("Invalid phone number")
        return value

    def validate(self, data):
        if not data.get("full_name"):
            raise serializers.ValidationError("Name is required")
        return data



class ChargeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Charge
        fields = "__all__"

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value

    def validate(self, data):
        if not data.get("charge_date"):
            raise serializers.ValidationError("Charge date required")
        return data