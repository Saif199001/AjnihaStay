from rest_framework import serializers

from .models import FinancialAdjustment


class FinancialAdjustmentCreateSerializer(serializers.Serializer):
    invoice = serializers.IntegerField(min_value=1)
    adjustment_type = serializers.ChoiceField(choices=FinancialAdjustment.ADJUSTMENT_TYPES)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)


class FinancialAdjustmentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    class Meta:
        model = FinancialAdjustment
        fields = [
            "id",
            "workspace",
            "invoice",
            "adjustment_type",
            "amount",
            "reason",
            "reference",
            "idempotency_key",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields
