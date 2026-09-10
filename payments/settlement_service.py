from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .adjustment_service import calculate_invoice_financial_position
from .authorization import require_mutation_permission
from .settlement_models import OccupancySettlement
from tenant.models import Occupancy


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def calculate_occupancy_settlement_position(occupancy, invoices):
    invoice_positions = [calculate_invoice_financial_position(invoice) for invoice in invoices]
    total_due = sum((position["outstanding"] for position in invoice_positions), Decimal("0"))
    security_deposit = _money(occupancy.security_deposit)
    return {
        "total_due": _money(total_due),
        "security_deposit": security_deposit,
        "invoice_positions": invoice_positions,
    }


def settle_occupancy(user, workspace, occupancy_id, outcome, refundable_deposit=Decimal("0")):
    require_mutation_permission(user, workspace)
    refundable_deposit = _money(refundable_deposit)

    if outcome not in dict(OccupancySettlement.OUTCOMES):
        raise ValidationError("Invalid settlement outcome")
    if refundable_deposit < 0:
        raise ValidationError("Refundable deposit cannot be negative")

    with transaction.atomic():
        workspace = type(workspace).objects.select_for_update().get(pk=workspace.pk)
        try:
            occupancy = Occupancy.objects.select_for_update().select_related("tenant", "unit").get(
                id=occupancy_id, tenant__workspace=workspace
            )
        except Occupancy.DoesNotExist:
            raise ValidationError("Occupancy not found")

        existing = OccupancySettlement.objects.filter(workspace=workspace, occupancy=occupancy).first()
        if existing:
            return existing, False

        if not occupancy.check_out_date:
            raise ValidationError("Occupancy must have a check-out date before settlement")

        invoices = list(occupancy.invoices.select_for_update().order_by("id"))
        position = calculate_occupancy_settlement_position(occupancy, invoices)
        total_due = position["total_due"]
        security_deposit = position["security_deposit"]

        if total_due != Decimal("0.00"):
            raise ValidationError("Occupancy has outstanding invoice balance")

        if outcome == OccupancySettlement.OUTCOME_NO_DEPOSIT:
            if security_deposit != Decimal("0.00") or refundable_deposit != Decimal("0.00"):
                raise ValidationError("No-deposit settlement requires zero deposit")
        elif outcome == OccupancySettlement.OUTCOME_FULL_REFUND:
            if refundable_deposit != security_deposit:
                raise ValidationError("Full-refund settlement must refund the full deposit")
        elif outcome == OccupancySettlement.OUTCOME_FULL_RETENTION:
            if refundable_deposit != Decimal("0.00"):
                raise ValidationError("Full-retention settlement cannot refund a deposit")
        elif outcome == OccupancySettlement.OUTCOME_PARTIAL_REFUND:
            if not (Decimal("0.00") < refundable_deposit < security_deposit):
                raise ValidationError("Partial-refund settlement must refund part of the deposit")

        retained_deposit = security_deposit - refundable_deposit
        settlement = OccupancySettlement.objects.create(
            workspace=workspace,
            occupancy=occupancy,
            state=OccupancySettlement.STATE_SETTLED,
            outcome=outcome,
            invoice_outstanding=total_due,
            security_deposit=security_deposit,
            refundable_deposit=refundable_deposit,
            retained_deposit=retained_deposit,
            settled_by=user,
        )
        return settlement, True
