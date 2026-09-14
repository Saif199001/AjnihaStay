from rest_framework import serializers

from .models import AgreementLink, KycDocument, KycDocumentEvent, KycProfile, KycVerificationEvent


class KycProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycProfile
        fields = [
            "id", "tenant", "workspace", "status", "verified_at", "verified_by",
            "rejected_at", "rejected_by", "rejection_reason", "created_at", "updated_at",
        ]
        read_only_fields = fields


class KycVerificationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycVerificationEvent
        fields = [
            "id", "kyc_profile", "tenant", "from_status", "to_status", "actor",
            "occurred_at", "reason", "metadata", "event_key", "created_at",
        ]
        read_only_fields = fields


class KycDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocument
        fields = [
            "id", "tenant", "workspace", "document_type", "document_number", "content_type",
            "file_size", "status", "issued_at", "expires_at", "uploaded_by", "uploaded_at",
            "verified_at", "verified_by", "rejected_at", "rejected_by", "rejection_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "tenant", "workspace", "content_type", "file_size", "status", "uploaded_by",
            "uploaded_at", "verified_at", "verified_by", "rejected_at", "rejected_by",
            "rejection_reason", "created_at", "updated_at",
        ]


class KycDocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.CharField(max_length=50)
    document_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    issued_at = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateField(required=False, allow_null=True)
    file = serializers.FileField(write_only=True)


class KycDocumentReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["under_review", "verify", "reject"])
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class KycRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class AgreementLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgreementLink
        fields = [
            "id", "tenant", "occupancy", "lease", "agreement_type", "reference",
            "metadata", "created_by", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_by", "created_at"]


class AgreementLinkCreateSerializer(serializers.Serializer):
    occupancy = serializers.IntegerField(min_value=1)
    agreement_type = serializers.CharField(max_length=50)
    reference = serializers.CharField(max_length=500, required=False, allow_blank=True)
    lease = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    metadata = serializers.JSONField(required=False)


class KycDocumentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocumentEvent
        fields = [
            "id", "document", "tenant", "from_status", "to_status", "actor",
            "occurred_at", "reason", "metadata", "event_key", "created_at",
        ]
        read_only_fields = fields
