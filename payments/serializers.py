from datetime import date
from decimal import Decimal

from rest_framework import serializers

from .billing_models import BillingSchedule
from .models import AdvanceCredit, AdvanceCreditApplication, Invoice, Payment, PaymentAllocation


class InvoiceSerializer(serializers.ModelSerializer):
    due_amount = serializers.ReadOnlyField()

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["id", "paid_amount", "status", "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    # These fields are used only when receiving a pure advance payment.
    # They are not persisted on Payment; the canonical service creates the
    # corresponding AdvanceCredit against the supplied tenant/occupancy.
    tenant = serializers.IntegerField(min_value=1, required=False, write_only=True)
    occupancy = serializers.IntegerField(min_value=1, required=False, allow_null=True, write_only=True)

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["id", "workspace", "created_at"]

    def validate(self, data):
        if data.get("amount") <= 0:
            raise serializers.ValidationError("Amount must be positive")
        if data.get("payment_date") > date.today():
            raise serializers.ValidationError("Invalid payment date")
        if data.get("invoice") in (None, "") and not data.get("tenant"):
            raise serializers.ValidationError({"tenant": "Tenant is required for a pure advance payment"})
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


class AdvanceCreditApplicationSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    class Meta:
        model = AdvanceCreditApplication
        fields = ["id", "credit", "invoice", "amount", "created_at"]
        read_only_fields = fields


class AdvanceCreditSerializer(serializers.ModelSerializer):
    original_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    available_amount = serializers.SerializerMethodField()
    applications = AdvanceCreditApplicationSerializer(many=True, read_only=True)

    class Meta:
        model = AdvanceCredit
        fields = [
            "id",
            "workspace",
            "tenant",
            "occupancy",
            "source_payment",
            "original_amount",
            "available_amount",
            "applications",
            "created_at",
        ]
        read_only_fields = fields

    def get_available_amount(self, obj):
        from .advance_credit_service import get_advance_credit_available_amount
        return f"{get_advance_credit_available_amount(obj):.2f}"


class AdvanceCreditInvoiceSerializer(InvoiceSerializer):
    paid_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    due_amount = serializers.SerializerMethodField()

    def get_due_amount(self, obj):
        return f"{obj.due_amount:.2f}"


class AdvanceCreditCreateSerializer(serializers.Serializer):
    payment = serializers.IntegerField(min_value=1)
    tenant = serializers.IntegerField(min_value=1)
    occupancy = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class AdvanceCreditApplicationCreateSerializer(serializers.Serializer):
    invoice = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
