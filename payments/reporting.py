"""Read-only financial reporting query boundary."""

from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .adjustment_service import calculate_invoice_financial_position
from .late_fee_models import LateFee
from .ledger_models import FinancialLedgerEntry
from .models import AdvanceCredit, FinancialAdjustment, Invoice, Payment

ZERO = Decimal("0.00")
REDUCING_ADJUSTMENT_TYPES = {"credit", "discount", "waiver", "write_off"}
AGING_BUCKETS = ("current", "1_30", "31_60", "61_90", "90_plus")


def _workspace_invoice_queryset(workspace):
    return Invoice.objects.filter(occupancy__tenant__workspace=workspace).select_related("occupancy")


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
        "reducing_adjustments": position["credit_adjustments"],
        "late_fee_total": position["late_fee_total"],
        "adjusted_receivable": position["adjusted_receivable"],
        "settlement": position["settlement"],
        "outstanding": position["outstanding"],
    }


def invoice_financial_report(*, workspace, invoice_id):
    invoice = _workspace_invoice_queryset(workspace).filter(pk=invoice_id).first()
    if invoice is None:
        raise ValidationError("Invoice not found in workspace.")
    return _invoice_projection(invoice)


def receivables_report(*, workspace, as_of=None):
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
    rows = [_invoice_projection(invoice) for invoice in _workspace_invoice_queryset(workspace)]
    return {
        status: {
            "count": sum(1 for row in rows if row["status"] == status),
            "outstanding": sum((row["outstanding"] for row in rows if row["status"] == status), ZERO),
        }
        for status in ("pending", "partial", "paid")
    }


def workspace_collection_summary(*, workspace):
    payment_total = Payment.objects.filter(workspace=workspace).aggregate(total=Sum("amount"))["total"] or ZERO
    refund_total = FinancialLedgerEntry.objects.filter(workspace=workspace, event_type="refund_succeeded").aggregate(total=Sum("amount"))["total"] or ZERO
    return {"payments_recorded": payment_total, "refunds_succeeded": refund_total, "net_collections": payment_total - refund_total}


def advance_credit_report(*, workspace):
    credits = AdvanceCredit.objects.filter(workspace=workspace).prefetch_related("applications")
    rows = []
    for credit in credits:
        applied = credit.applications.aggregate(total=Sum("amount"))["total"] or ZERO
        rows.append({"advance_credit_id": credit.pk, "payment_id": credit.payment_id, "original_amount": credit.original_amount, "applied_amount": applied, "available_amount": max(credit.original_amount - applied, ZERO)})
    return {"count": len(rows), "original_amount": sum((r["original_amount"] for r in rows), ZERO), "applied_amount": sum((r["applied_amount"] for r in rows), ZERO), "available_amount": sum((r["available_amount"] for r in rows), ZERO), "credits": rows}


def adjustment_report(*, workspace):
    result = {}
    types = FinancialAdjustment.objects.filter(workspace=workspace).values_list("adjustment_type", flat=True).distinct()
    for adjustment_type in types:
        qs = FinancialAdjustment.objects.filter(workspace=workspace, adjustment_type=adjustment_type)
        result[adjustment_type] = {"count": qs.count(), "amount": qs.aggregate(total=Sum("amount"))["total"] or ZERO, "kind": "reducing" if adjustment_type in REDUCING_ADJUSTMENT_TYPES else "debit"}
    return result


def late_fee_report(*, workspace):
    rows = LateFee.objects.filter(workspace=workspace).values("calculation_mode").annotate(total=Sum("amount")).order_by("calculation_mode")
    return {row["calculation_mode"]: {"count": LateFee.objects.filter(workspace=workspace, calculation_mode=row["calculation_mode"]).count(), "amount": row["total"] or ZERO} for row in rows}


def _coerce_date(value, field_name):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValidationError(f"Invalid {field_name} date")


def collection_period_report(*, workspace, start, end):
    start = _coerce_date(start, "start")
    end = _coerce_date(end, "end")
    if start > end:
        raise ValidationError("Start date cannot be after end date")
    payment_total = Payment.objects.filter(workspace=workspace, payment_date__range=(start, end)).aggregate(total=Sum("amount"))["total"] or ZERO
    refund_total = FinancialLedgerEntry.objects.filter(workspace=workspace, event_type="refund_succeeded", occurred_at__date__range=(start, end)).aggregate(total=Sum("amount"))["total"] or ZERO
    return {"start": start, "end": end, "payments_recorded": payment_total, "refunds_succeeded": refund_total, "net_collections": payment_total - refund_total}


def _aging_bucket(days_overdue):
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "90_plus"


def aging_report(*, workspace, as_of):
    as_of = _coerce_date(as_of, "as_of")
    buckets = {bucket: {"count": 0, "outstanding": ZERO, "invoices": []} for bucket in AGING_BUCKETS}
    for invoice in _workspace_invoice_queryset(workspace).order_by("due_date", "pk"):
        projection = _invoice_projection(invoice)
        outstanding = projection["outstanding"]
        if outstanding <= 0:
            continue
        days = (as_of - invoice.due_date).days
        bucket = _aging_bucket(days)
        buckets[bucket]["count"] += 1
        buckets[bucket]["outstanding"] += outstanding
        buckets[bucket]["invoices"].append({"invoice_id": invoice.pk, "invoice_number": invoice.invoice_number, "due_date": invoice.due_date, "outstanding": outstanding, "days_overdue": max(days, 0)})
    return {"as_of": as_of, "buckets": buckets, "total_outstanding": sum((b["outstanding"] for b in buckets.values()), ZERO), "invoice_count": sum((b["count"] for b in buckets.values()), 0)}


def workspace_ledger_activity(*, workspace, start=None, end=None):
    queryset = FinancialLedgerEntry.objects.filter(workspace=workspace).order_by("occurred_at", "pk")
    if start is not None:
        queryset = queryset.filter(occurred_at__gte=start)
    if end is not None:
        queryset = queryset.filter(occurred_at__lte=end)
    return queryset
