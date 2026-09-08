from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission

from .adjustment_service import create_financial_adjustment
from .adjustment_serializers import (
    FinancialAdjustmentCreateSerializer,
    FinancialAdjustmentSerializer,
)


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def financial_adjustment_create_api(request):
    serializer = FinancialAdjustmentCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    try:
        adjustment, position, created = create_financial_adjustment(
            request.user,
            request.workspace,
            serializer.validated_data,
        )
    except ValidationError as exc:
        message = _validation_message(exc)
        if message == "Invoice not found":
            return Response({"error": message}, status=404)
        return Response({"error": message}, status=400)

    return Response(
        {
            "message": "Financial adjustment created" if created else "Financial adjustment already exists",
            "data": {
                "adjustment": FinancialAdjustmentSerializer(adjustment).data,
                "financial_position": {
                    "gross_receivable": f"{position['gross_receivable']:.2f}",
                    "debit_adjustments": f"{position['debit_adjustments']:.2f}",
                    "credit_adjustments": f"{position['credit_adjustments']:.2f}",
                    "adjusted_receivable": f"{position['adjusted_receivable']:.2f}",
                    "settlement": f"{position['settlement']:.2f}",
                    "outstanding": f"{position['outstanding']:.2f}",
                    "status": position["status"],
                },
                "created": created,
            },
        },
        status=201,
    )
