from rest_framework import serializers
from .models import Invoice, Payment
from datetime import date


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
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        if data.get("amount") <= 0:
            raise serializers.ValidationError("Amount must be positive")
        if data.get("payment_date") > date.today():
            raise serializers.ValidationError("Invalid payment date")
        return data
