from rest_framework import serializers

from .lifecycle_models import LeaseNotice
from .models import Lease


class LeaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lease
        fields = [
            "id", "workspace", "occupancy", "agreement_number", "start_date", "end_date",
            "rent_amount", "security_deposit", "notice_period_days", "status", "terms",
            "agreement_reference", "created_by", "updated_by", "created_at", "updated_at",
            "activated_at", "terminated_at", "cancelled_at",
        ]
        read_only_fields = [
            "id", "workspace", "created_by", "updated_by", "created_at", "updated_at",
            "activated_at", "terminated_at", "cancelled_at", "status",
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
            raise serializers.ValidationError("Lease end date cannot be before lease start date")
        return data


class LeaseTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Lease.STATUS_CHOICES)


class LeaseLifecycleActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=False, max_length=500)
    effective_date = serializers.DateField(required=False)


class LeaseNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaseNotice
        fields = [
            "id", "workspace", "lease", "notice_date", "effective_date", "notice_type",
            "reason", "status", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "lease", "status", "created_by", "created_at", "updated_at"]

    def validate(self, data):
        if data.get("effective_date") and data.get("notice_date") and data["effective_date"] < data["notice_date"]:
            raise serializers.ValidationError("Notice effective date cannot be before notice date")
        return data


class LeaseNoticeTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LeaseNotice.STATUS_CHOICES)
