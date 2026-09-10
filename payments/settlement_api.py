from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission
from .financial_transition_service import FinancialTransition, execute_transition
from .settlement_models import OccupancySettlement


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def occupancy_settlement_create_api(request, occupancy_id):
    outcome = request.data.get("outcome")
    try:
        refundable_deposit = Decimal(request.data.get("refundable_deposit", "0.00"))
    except (TypeError, ValueError, InvalidOperation):
        return Response({"error": "Invalid refundable deposit amount"}, status=400)

    try:
        settlement, created = execute_transition(
            FinancialTransition.SETTLE_OCCUPANCY,
            user=request.user,
            workspace=request.workspace,
            occupancy_id=occupancy_id,
            outcome=outcome,
            refundable_deposit=refundable_deposit,
        )
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)

    data = {
        "id": settlement.id,
        "occupancy": settlement.occupancy_id,
        "state": settlement.state,
        "outcome": settlement.outcome,
        "invoice_outstanding": f"{settlement.invoice_outstanding:.2f}",
        "security_deposit": f"{settlement.security_deposit:.2f}",
        "refundable_deposit": f"{settlement.refundable_deposit:.2f}",
        "retained_deposit": f"{settlement.retained_deposit:.2f}",
        "settled_by": settlement.settled_by_id,
        "settled_at": settlement.settled_at,
    }
    return Response(
        {"message": "Occupancy settled" if created else "Occupancy already settled", "created": created, "data": data},
        status=201 if created else 200,
    )
