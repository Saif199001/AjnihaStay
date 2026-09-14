from rest_framework import serializers

from .models import Applicant, Application, ApplicationEvent


class ApplicantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Applicant
        fields = ["id", "full_name", "phone", "email", "address", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.CharField(source="applicant.full_name", read_only=True)
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "applicant", "applicant_name", "property", "property_name", "unit", "subunit",
            "requested_check_in_date", "requested_check_out_date", "status", "submitted_at",
            "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "applicant_name", "property_name", "status", "submitted_at", "reviewed_at",
            "decided_at", "rejection_reason", "withdrawal_reason", "created_by", "updated_by",
            "created_at", "updated_at",
        ]


class ApplicationEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = ApplicationEvent
        fields = [
            "id", "from_status", "to_status", "actor", "actor_name", "occurred_at",
            "reason", "metadata", "event_key", "created_at",
        ]
        read_only_fields = fields
