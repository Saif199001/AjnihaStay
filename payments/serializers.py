from datetime import date

from rest_framework import serializers

from .billing_models import BillingSchedule
from .models import Invoice, Payment, PaymentAllocation


class InvoiceSerializer(serializers.ModelSerializer):
    due_amount = serializers.ReadOnlyField()

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["id", "paid_amount", "status", "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["id", "workspace", "created_at"]

    def validate(self, data):
        if data.get("amount") <= 0:
            raise serializers.ValidationError("Amount must be positive")
        if data.get("payment_date") > date.today():
            raise serializers.ValidationError("Invalid payment date")
        return data


class PaymentAllocationRequestSerializer(serializers.Serializer):
    invoice = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class PaymentAllocationCreateSerializer(serializers.Serializer):
    allocations = PaymentAllocationRequestSerializer(many=True, allow_empty=False)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ["id", "payment", "invoice", "amount", "created_at"]
        read_only_fields = fields


class BillingScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingSchedule
        fields = [
            "id",
            "occupancy",
            "frequency",
            "amount",
            "next_run_date",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
