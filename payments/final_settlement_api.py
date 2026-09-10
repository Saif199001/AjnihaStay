from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission
from .final_settlement import FinalSettlement, finalize_final_settlement


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def final_settlement_finalize_api(request, occupancy_id):
    refundable_deposit = request.data.get("refundable_deposit")
    if refundable_deposit is not None:
        try:
            refundable_deposit = Decimal(refundable_deposit)
        except Exception:
            return Response({"error": "Invalid refundable deposit amount"}, status=400)

    try:
        settlement = finalize_final_settlement(
            request.user,
            request.workspace,
            occupancy_id,
            refundable_deposit=refundable_deposit,
        )
    except ValidationError as exc:
        return Response({"error": exc.messages[0] if exc.messages else str(exc)}, status=400)

    return Response(
        {
            "message": "Final settlement completed",
            "data": {
                "id": settlement.id,
                "occupancy": settlement.occupancy_id,
                "total_rent": f"{settlement.total_rent:.2f}",
                "total_charges": f"{settlement.total_charges:.2f}",
                "total_paid": f"{settlement.total_paid:.2f}",
                "total_due": f"{settlement.total_due:.2f}",
                "security_deposit": f"{settlement.security_deposit:.2f}",
                "retained_deposit": f"{settlement.retained_deposit:.2f}",
                "refundable_deposit": f"{settlement.refundable_deposit:.2f}",
                "final_balance": f"{settlement.final_balance:.2f}",
                "outcome": settlement.outcome,
                "settled_by": settlement.settled_by_id,
                "settled_at": settlement.settled_at,
            },
        },
        status=201,
    )
