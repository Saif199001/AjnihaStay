from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission

from .refund_models import PaymentRefund
from .refund_serializers import (
    PaymentRefundCreateSerializer,
    PaymentRefundSerializer,
    PaymentRefundTransitionSerializer,
)
from .refund_service import request_payment_refund, transition_payment_refund


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def payment_refund_create_api(request, payment_id):
    serializer = PaymentRefundCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data
    try:
        refund = request_payment_refund(
            user=request.user,
            workspace=request.workspace,
            payment=payment_id,
            amount=data["amount"],
            reason=data["reason"],
            reference=data.get("reference"),
            idempotency_key=data.get("idempotency_key"),
        )
    except ValidationError as exc:
        message = _validation_message(exc)
        if message == "Payment not found":
            return Response({"error": message}, status=404)
        return Response({"error": message}, status=400)

    return Response(
        {
            "message": "Payment refund requested",
            "data": PaymentRefundSerializer(refund).data,
        },
        status=201,
    )


@api_view(["PATCH"])
@permission_classes([WorkspaceManagerPermission])
def payment_refund_transition_api(request, refund_id):
    serializer = PaymentRefundTransitionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data
    try:
        refund = transition_payment_refund(
            user=request.user,
            workspace=request.workspace,
            refund=refund_id,
            status=data["status"],
            failure_reason=data.get("failure_reason"),
        )
    except ValidationError as exc:
        message = _validation_message(exc)
        if message == "Refund not found":
            return Response({"error": message}, status=404)
        return Response({"error": message}, status=400)

    return Response(
        {
            "message": "Payment refund status updated",
            "data": PaymentRefundSerializer(refund).data,
        }
    )
