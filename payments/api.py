from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .advance_credit_service import (
    apply_advance_credit,
    create_advance_credit,
    get_advance_credit,
    get_advance_credits,
)
from .allocation_service import allocate_payment
from .billing_service import (
    create_billing_schedule,
    get_billing_schedule,
    get_billing_schedules,
    update_billing_schedule,
)
from .serializers import (
    AdvanceCreditApplicationCreateSerializer,
    AdvanceCreditApplicationSerializer,
    AdvanceCreditCreateSerializer,
    AdvanceCreditSerializer,
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


@api_view(["GET", "POST"])
@permission_classes([WorkspaceStaffPermission])
def advance_credit_collection_api(request):
    if request.method == "GET":
        credits = get_advance_credits(request.workspace)
        return Response({"data": AdvanceCreditSerializer(credits, many=True).data})

    if not WorkspaceManagerPermission().has_permission(request, None):
        return Response({"detail": "You do not have permission to perform this action."}, status=403)

    serializer = AdvanceCreditCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        credit = create_advance_credit(
            request.user,
            request.workspace,
            serializer.validated_data,
        )
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    credit = get_advance_credit(credit.id, request.workspace)
    return Response(
        {"message": "Advance credit created", "data": AdvanceCreditSerializer(credit).data},
        status=201,
    )


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def advance_credit_detail_api(request, credit_id):
    try:
        credit = get_advance_credit(credit_id, request.workspace)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
    return Response({"data": AdvanceCreditSerializer(credit).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def advance_credit_apply_api(request, credit_id):
    serializer = AdvanceCreditApplicationCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = dict(serializer.validated_data)
    data["credit"] = credit_id
    try:
        application, remaining_credit, invoice = apply_advance_credit(
            request.user,
            request.workspace,
            data,
        )
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)

    return Response(
        {
            "message": "Advance credit applied",
            "data": {
                "application": AdvanceCreditApplicationSerializer(application).data,
                "remaining_credit": remaining_credit,
                "invoice": InvoiceSerializer(invoice).data,
            },
        },
        status=201,
    )
