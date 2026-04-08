from rest_framework import serializers
from .models import Invoice, Payment


class InvoiceSerializer(serializers.ModelSerializer):

    due_amount = serializers.ReadOnlyField()

    class Meta:
        model = Invoice
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Payment
        fields = "__all__"