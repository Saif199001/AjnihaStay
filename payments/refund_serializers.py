from rest_framework import serializers

from .refund_models import PaymentRefund


class PaymentRefundCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)


class PaymentRefundTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=PaymentRefund.STATUS_CHOICES)
    failure_reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class PaymentRefundSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    class Meta:
        model = PaymentRefund
        fields = [
            "id",
            "workspace",
            "payment",
            "amount",
            "status",
            "reason",
            "reference",
            "idempotency_key",
            "failure_reason",
            "requested_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
