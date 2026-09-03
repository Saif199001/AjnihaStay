from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .serializers import InvoiceSerializer, PaymentSerializer
from .services import (
    calculate_final_settlement,
    create_payment,
    get_invoice,
    get_invoices,
    get_payments,
)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invoice_create_api(request):
    return Response({"error": "Invoice creation is disabled"}, status=403)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def invoice_list_api(request):
    return Response({"data": InvoiceSerializer(get_invoices(request.workspace), many=True).data})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def invoice_detail_api(request, invoice_id):
    try:
        invoice = get_invoice(invoice_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=404)
    return Response({"data": InvoiceSerializer(invoice).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def payment_create_api(request):
    serializer = PaymentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        payment = create_payment(request.user, request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"message": "Payment created", "data": PaymentSerializer(payment).data})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def payment_list_api(request):
    invoice_id = request.GET.get("invoice")
    try:
        payments = get_payments(invoice_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"data": PaymentSerializer(payments, many=True).data})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def final_settlement_api(request, occupancy_id):
    try:
        data = calculate_final_settlement(occupancy_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": str(exc)}, status=404)
    return Response({"data": data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_invoice_api(request):
    return Response({"error": "Recurring invoice generation is disabled"}, status=403)
