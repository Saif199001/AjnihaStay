from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .allocation_service import allocate_payment
from .billing_service import (
    create_billing_schedule,
    get_billing_schedule,
    get_billing_schedules,
    update_billing_schedule,
)
from .serializers import (
    BillingScheduleSerializer,
    InvoiceSerializer,
    PaymentAllocationCreateSerializer,
    PaymentAllocationSerializer,
    PaymentSerializer,
)
from .services import (
    calculate_final_settlement,
    get_invoice,
    get_invoices,
    get_payments,
    record_payment,
)


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


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
        return Response({"error": _validation_message(exc)}, status=404)
    return Response({"data": InvoiceSerializer(invoice).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def payment_create_api(request):
    serializer = PaymentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        payment = record_payment(request.user, request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Payment created", "data": PaymentSerializer(payment).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def payment_allocation_create_api(request, payment_id):
    serializer = PaymentAllocationCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        allocations = allocate_payment(
            request.user,
            request.workspace,
            payment_id,
            serializer.validated_data["allocations"],
        )
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)

    return Response(
        {
            "message": "Payment allocated",
            "data": PaymentAllocationSerializer(allocations, many=True).data,
        },
        status=201,
    )


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def payment_list_api(request):
    invoice_id = request.GET.get("invoice")
    try:
        payments = get_payments(invoice_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"data": PaymentSerializer(payments, many=True).data})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def final_settlement_api(request, occupancy_id):
    try:
        data = calculate_final_settlement(occupancy_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
    return Response({"data": data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_invoice_api(request):
    return Response({"error": "Recurring invoice generation is disabled"}, status=403)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def billing_schedule_list_api(request):
    schedules = get_billing_schedules(request.workspace)
    return Response({"data": BillingScheduleSerializer(schedules, many=True).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def billing_schedule_create_api(request):
    serializer = BillingScheduleSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        schedule = create_billing_schedule(request.user, request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Billing schedule created", "data": BillingScheduleSerializer(schedule).data}, status=201)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def billing_schedule_detail_api(request, schedule_id):
    try:
        schedule = get_billing_schedule(schedule_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
    return Response({"data": BillingScheduleSerializer(schedule).data})


@api_view(["PATCH"])
@permission_classes([WorkspaceManagerPermission])
def billing_schedule_update_api(request, schedule_id):
    try:
        schedule = get_billing_schedule(schedule_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
    serializer = BillingScheduleSerializer(schedule, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        schedule = update_billing_schedule(
            request.user,
            request.workspace,
            schedule_id,
            serializer.validated_data,
        )
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Billing schedule updated", "data": BillingScheduleSerializer(schedule).data})
