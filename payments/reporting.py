"""Read-only financial reporting query boundary.

P0.12-A deliberately contains no financial mutation logic.  These helpers
compose existing canonical financial-position calculations and the immutable
financial subledger without changing authoritative domain state.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .adjustment_service import calculate_invoice_financial_position
from .models import Invoice, Payment
from .ledger_models import FinancialLedgerEntry

ZERO = Decimal("0.00")


def _workspace_invoice_queryset(workspace):
    return Invoice.objects.filter(workspace=workspace).select_related("occupancy")


def invoice_financial_report(*, workspace, invoice_id):
    """Return one canonical invoice financial projection without mutation."""
    invoice = _workspace_invoice_queryset(workspace).filter(pk=invoice_id).first()
    if invoice is None:
        raise ValidationError("Invoice not found in workspace.")

    position = calculate_invoice_financial_position(invoice)
    return {
        "invoice_id": invoice.pk,
        "occupancy_id": invoice.occupancy_id,
        "gross_receivable": position["gross_receivable"],
        "debit_adjustments": position["debit_adjustments"],
        "reducing_adjustments": position["reducing_adjustments"],
        "late_fee_total": position["late_fee_total"],
        "adjusted_receivable": position["adjusted_receivable"],
        "settlement": position["settlement"],
        "outstanding": position["outstanding"],
    }


def workspace_collection_summary(*, workspace):
    """Return read-only payment/refund collection totals for a workspace."""
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
