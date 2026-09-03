from rest_framework import serializers

from payments.serializers import InvoiceSerializer
from .models import Charge, Occupancy, Tenant


class OccupancySerializer(serializers.ModelSerializer):
    invoices = InvoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Occupancy
        fields = "__all__"
        read_only_fields = ["id", "allotted_by", "created_at", "updated_at"]

    def validate_rent(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("Rent cannot be negative")
        return value

    def validate_security_deposit(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("Security deposit cannot be negative")
        return value

    def validate(self, data):
        check_in = data.get("check_in_date")
        check_out = data.get("check_out_date")
        next_due = data.get("next_due_date")

        if check_in and check_out and check_out < check_in:
            raise serializers.ValidationError("Check-out date cannot be before check-in date")
        if check_in and next_due and next_due < check_in:
            raise serializers.ValidationError("Next due date cannot be before check-in date")
        return data


class TenantSerializer(serializers.ModelSerializer):
    occupancies = OccupancySerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = "__all__"
        read_only_fields = ["id", "owner", "workspace", "created_at", "updated_at"]

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
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value

    def validate(self, data):
        if not data.get("charge_date"):
            raise serializers.ValidationError("Charge date required")
        return data
