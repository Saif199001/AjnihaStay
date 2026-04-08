from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from .services import (
    create_invoice,
    get_invoices,
    get_invoice,
    create_payment,
    get_payments
)

from .serializers import InvoiceSerializer, PaymentSerializer

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invoice_create_api(request):

    try:
        invoice = create_invoice(request.data)
        serializer = InvoiceSerializer(invoice)

        return Response(serializer.data)

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def invoice_list_api(request):

    invoices = get_invoices(request.user)
    serializer = InvoiceSerializer(invoices, many=True)

    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def invoice_detail_api(request, invoice_id):

    try:
        invoice = get_invoice(invoice_id, request.user)
        serializer = InvoiceSerializer(invoice)

        return Response(serializer.data)

    except ValidationError as e:
        return Response({"error": str(e)}, status=404)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_create_api(request):

    try:
        create_payment(request.user, request.data)
        serializer = PaymentSerializer(payment)

        return Response(serializer.data)

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_list_api(request):

    invoice_id = request.GET.get("invoice")

    payments = get_payments(invoice_id, request.user)
    serializer = PaymentSerializer(payments, many=True)

    return Response(serializer.data)