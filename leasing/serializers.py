from rest_framework import serializers

from .models import Lease


class LeaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lease
        fields = "__all__"
        read_only_fields = [
            "id",
            "workspace",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "activated_at",
            "terminated_at",
            "cancelled_at",
        ]

    def validate_rent_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Rent amount cannot be negative")
        return value

    def validate_security_deposit(self, value):
        if value < 0:
            raise serializers.ValidationError("Security deposit cannot be negative")
        return value

    def validate(self, data):
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError("Lease end date cannot be before start date")
        if data.get("status") not in (None, Lease.STATUS_DRAFT):
            raise serializers.ValidationError("New leases must start in draft status")
        return data


class LeaseTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Lease.STATUS_CHOICES)
