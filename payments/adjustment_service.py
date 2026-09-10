from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .authorization import MUTATION_ROLES, require_mutation_permission
from .models import AdvanceCreditApplication, FinancialAdjustment, Invoice, PaymentAllocation


def _positive_decimal(value, field_name):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError(f"Invalid {field_name} amount")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(f"{field_name.capitalize()} amount must be greater than zero")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError(f"{field_name.capitalize()} amount cannot have more than two decimal places")
    return amount


def _positive_id(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name} ID")
    if parsed <= 0:
        raise ValidationError(f"Invalid {field_name} ID")
    return parsed


def _require_mutation_permission(user, workspace):
    """Backward-compatible alias for the shared financial mutation guard."""
    return require_mutation_permission(user, workspace)


def _sum_adjustments(invoice):
    rows = FinancialAdjustment.objects.filter(invoice=invoice).values("adjustment_type").annotate(
        total=Sum("amount")
    )
    totals = {row["adjustment_type"]: row["total"] or Decimal("0") for row in rows}

    debit = totals.get(FinancialAdjustment.TYPE_DEBIT, Decimal("0"))
    credit = sum(
        (
            totals.get(FinancialAdjustment.TYPE_CREDIT, Decimal("0")),
            totals.get(FinancialAdjustment.TYPE_DISCOUNT, Decimal("0")),
            totals.get(FinancialAdjustment.TYPE_WAIVER, Decimal("0")),
            totals.get(FinancialAdjustment.TYPE_WRITE_OFF, Decimal("0")),
        ),
        Decimal("0"),
    )
    return debit, credit, totals


def calculate_invoice_financial_position(invoice):
    """Return the canonical invoice receivable and settlement position."""
    gross_receivable = invoice.total_amount or Decimal("0")
    debit_adjustments, credit_adjustments, adjustment_totals = _sum_adjustments(invoice)
    adjusted_receivable = gross_receivable + debit_adjustments - credit_adjustments

    payment_settlement = (
        PaymentAllocation.objects.filter(invoice=invoice).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    advance_credit_settlement = (
        AdvanceCreditApplication.objects.filter(invoice=invoice).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    settlement = payment_settlement + advance_credit_settlement
    outstanding = max(adjusted_receivable - settlement, Decimal("0"))

    if adjusted_receivable > 0:
        if settlement == adjusted_receivable:
            status = "paid"
        elif settlement > 0:
            status = "partial"
        else:
            status = "pending"
    else:
        status = "pending"

    return {
        "gross_receivable": gross_receivable,
        "debit_adjustments": debit_adjustments,
        "credit_adjustments": credit_adjustments,
        "adjustment_totals": adjustment_totals,
        "adjusted_receivable": adjusted_receivable,
        "payment_settlement": payment_settlement,
        "advance_credit_settlement": advance_credit_settlement,
        "settlement": settlement,
        "outstanding": outstanding,
        "status": status,
    }


def _same_idempotent_operation(existing, *, invoice, adjustment_type, amount, reason, reference):
    return (
        existing.invoice_id == invoice.id
        and existing.adjustment_type == adjustment_type
        and existing.amount == amount
        and existing.reason == reason
        and existing.reference == reference
    )


def create_financial_adjustment(user, workspace, data):
    """Create an immutable receivable-side adjustment through the canonical service."""
    _require_mutation_permission(user, workspace)

    invoice_id = _positive_id(data.get("invoice"), "invoice")
    adjustment_type = data.get("adjustment_type")
    amount = _positive_decimal(data.get("amount"), "adjustment")
    reason = data.get("reason")
    reference = data.get("reference")
    idempotency_key = data.get("idempotency_key")

    if adjustment_type not in dict(FinancialAdjustment.ADJUSTMENT_TYPES):
        raise ValidationError("Invalid adjustment type")
    if not reason or not reason.strip():
        raise ValidationError("Adjustment reason is required")
    if idempotency_key is not None:
        idempotency_key = str(idempotency_key).strip()
        if not idempotency_key:
            idempotency_key = None

    with transaction.atomic():
        if idempotency_key:
            from workspaces.models import Workspace
            workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)

        try:
            invoice = Invoice.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(
                id=invoice_id,
                occupancy__tenant__workspace=workspace,
            )
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        if idempotency_key:
            existing = FinancialAdjustment.objects.filter(
                workspace=workspace,
                idempotency_key=idempotency_key,
            ).first()
            if existing:
                if not _same_idempotent_operation(
                    existing,
                    invoice=invoice,
                    adjustment_type=adjustment_type,
                    amount=amount,
                    reason=reason,
                    reference=reference,
                ):
                    raise ValidationError("Idempotency key already used for a different adjustment")
                return existing, calculate_invoice_financial_position(invoice), False

        position = calculate_invoice_financial_position(invoice)

        reducing_types = {
            FinancialAdjustment.TYPE_CREDIT,
            FinancialAdjustment.TYPE_DISCOUNT,
            FinancialAdjustment.TYPE_WAIVER,
            FinancialAdjustment.TYPE_WRITE_OFF,
        }
        if adjustment_type in reducing_types:
            remaining_collectible = position["adjusted_receivable"] - position["settlement"]
            if amount > remaining_collectible:
                raise ValidationError("Adjustment exceeds remaining collectible balance")

        adjustment = FinancialAdjustment.objects.create(
            workspace=workspace,
            invoice=invoice,
            adjustment_type=adjustment_type,
            amount=amount,
            reason=reason.strip(),
            reference=reference,
            idempotency_key=idempotency_key,
            created_by=user,
        )

        position = calculate_invoice_financial_position(invoice)
        Invoice.objects.filter(id=invoice.id).update(
            paid_amount=position["settlement"],
            status=position["status"],
        )
        invoice.paid_amount = position["settlement"]
        invoice.status = position["status"]

        return adjustment, position, True
