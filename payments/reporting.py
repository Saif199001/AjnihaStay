"""Read-only financial reporting query boundary.

P0.12 reporting is projection-only: authoritative financial state and the
immutable ledger are queried, never mutated.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .adjustment_service import calculate_invoice_financial_position
from .late_fee_models import LateFee
from .ledger_models import FinancialLedgerEntry
from .models import AdvanceCredit, FinancialAdjustment, Invoice, Payment

ZERO = Decimal("0.00")
REDUCING_ADJUSTMENT_TYPES = {"credit", "discount", "waiver", "write_off"}


def _workspace_invoice_queryset(workspace):
    return Invoice.objects.filter(occupancy__tenant__workspace=workspace).select_related(
        "occupancy"
    )


def _invoice_projection(invoice):
    position = calculate_invoice_financial_position(invoice)
    return {
        "invoice_id": invoice.pk,
        "invoice_number": invoice.invoice_number,
        "occupancy_id": invoice.occupancy_id,
        "billing_start": invoice.billing_start,
        "billing_end": invoice.billing_end,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "gross_receivable": position["gross_receivable"],
        "debit_adjustments": position["debit_adjustments"],
        "reducing_adjustments": position["reducing_adjustments"],
        "late_fee_total": position["late_fee_total"],
        "adjusted_receivable": position["adjusted_receivable"],
        "settlement": position["settlement"],
        "outstanding": position["outstanding"],
    }


def invoice_financial_report(*, workspace, invoice_id):
    """Return one canonical invoice financial projection without mutation."""
    invoice = _workspace_invoice_queryset(workspace).filter(pk=invoice_id).first()
    if invoice is None:
        raise ValidationError("Invoice not found in workspace.")
    return _invoice_projection(invoice)


def receivables_report(*, workspace, as_of=None):
    """Return invoice-level receivable projections scoped to a workspace.

    ``as_of`` is accepted as a reporting contract boundary. Current financial
    facts are used; historical reconstruction is deferred to period reporting.
    """
    invoices = _workspace_invoice_queryset(workspace).order_by("due_date", "pk")
    rows = [_invoice_projection(invoice) for invoice in invoices]
    return {
        "as_of": as_of,
        "count": len(rows),
        "gross_receivable": sum((r["gross_receivable"] for r in rows), ZERO),
        "adjusted_receivable": sum((r["adjusted_receivable"] for r in rows), ZERO),
        "settlement": sum((r["settlement"] for r in rows), ZERO),
        "outstanding": sum((r["outstanding"] for r in rows), ZERO),
        "invoices": rows,
    }


def invoice_status_report(*, workspace):
    """Return invoice counts and outstanding totals by canonical status."""
    rows = [_invoice_projection(invoice) for invoice in _workspace_invoice_queryset(workspace)]
    result = {}
    for status in ("pending", "partial", "paid"):
        matching = [row for row in rows if row["status"] == status]
        result[status] = {
            "count": len(matching),
            "outstanding": sum((r["outstanding"] for r in matching), ZERO),
        }
    return result


def workspace_collection_summary(*, workspace):
    """Return read-only recorded cash and successful refund totals."""
    payment_total = (
        Payment.objects.filter(workspace=workspace).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    refund_total = (
        FinancialLedgerEntry.objects.filter(
            workspace=workspace,
            event_type=FinancialLedgerEntry.REFUND_SUCCEEDED,
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    return {
        "payments_recorded": payment_total,
        "refunds_succeeded": refund_total,
        "net_collections": payment_total - refund_total,
    }


def advance_credit_report(*, workspace):
    """Return prepaid/advance-credit balances without changing credits."""
    credits = AdvanceCredit.objects.filter(workspace=workspace).prefetch_related("applications")
    rows = []
    for credit in credits:
        applied = credit.applications.aggregate(total=Sum("amount"))["total"] or ZERO
        rows.append(
            {
                "advance_credit_id": credit.pk,
                "payment_id": credit.payment_id,
                "original_amount": credit.original_amount,
                "applied_amount": applied,
                "available_amount": max(credit.original_amount - applied, ZERO),
            }
        )
    return {
        "count": len(rows),
        "original_amount": sum((r["original_amount"] for r in rows), ZERO),
        "applied_amount": sum((r["applied_amount"] for r in rows), ZERO),
        "available_amount": sum((r["available_amount"] for r in rows), ZERO),
        "credits": rows,
    }


def adjustment_report(*, workspace):
    """Return immutable adjustment totals by type."""
    result = {}
    types = FinancialAdjustment.objects.filter(workspace=workspace).values_list(
        "adjustment_type", flat=True
    ).distinct()
    for adjustment_type in types:
        qs = FinancialAdjustment.objects.filter(
            workspace=workspace, adjustment_type=adjustment_type
        )
        result[adjustment_type] = {
            "count": qs.count(),
            "amount": qs.aggregate(total=Sum("amount"))["total"] or ZERO,
            "kind": "reducing" if adjustment_type in REDUCING_ADJUSTMENT_TYPES else "debit",
        }
    return result


def late_fee_report(*, workspace):
    """Return immutable generated late-fee totals by calculation mode."""
    rows = (
        LateFee.objects.filter(workspace=workspace)
        .values("calculation_mode")
        .annotate(total=Sum("amount"))
        .order_by("calculation_mode")
    )
    return {
        row["calculation_mode"]: {
            "count": LateFee.objects.filter(
                workspace=workspace, calculation_mode=row["calculation_mode"]
            ).count(),
            "amount": row["total"] or ZERO,
        }
        for row in rows
    }


def workspace_ledger_activity(*, workspace, start=None, end=None):
    """Return immutable ledger activity scoped to one workspace and period."""
    queryset = FinancialLedgerEntry.objects.filter(workspace=workspace).order_by(
        "occurred_at", "pk"
    )
    if start is not None:
        queryset = queryset.filter(occurred_at__gte=start)
    if end is not None:
        queryset = queryset.filter(occurred_at__lte=end)
    return queryset
