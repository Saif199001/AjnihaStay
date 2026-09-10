"""Canonical invoice lifecycle state handling.

This module extends the existing invoice contract without changing its persisted
status choices. Invoice ``status`` remains the canonical settlement state
(pending/partial/paid); overdue is a derived lifecycle condition based on the
due date and outstanding balance.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .adjustment_service import calculate_invoice_financial_position
from .models import Invoice


LIFECYCLE_STATUSES = frozenset({"pending", "partial", "paid"})


def _as_date(value):
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    raise ValidationError("Evaluation date must be a date")


def get_invoice_lifecycle(invoice, *, as_of=None):
    """Return the derived lifecycle view without mutating historical facts."""
    evaluation_date = _as_date(as_of)
    position = calculate_invoice_financial_position(invoice)
    status = position["status"]

    if status not in LIFECYCLE_STATUSES:
        raise ValidationError("Invalid canonical invoice status")

    outstanding = position["outstanding"]
    overdue = bool(outstanding > Decimal("0") and evaluation_date > invoice.due_date)

    return {
        "status": status,
        "overdue": overdue,
        "outstanding": outstanding,
        "settlement": position["settlement"],
        "due_date": invoice.due_date,
    }


def refresh_invoice_lifecycle(invoice_id, workspace, *, as_of=None):
    """Lock, recompute and persist the canonical derived invoice state."""
    with transaction.atomic():
        try:
            invoice = Invoice.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(
                id=invoice_id,
                occupancy__tenant__workspace=workspace,
            )
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        position = calculate_invoice_financial_position(invoice)
        if position["status"] not in LIFECYCLE_STATUSES:
            raise ValidationError("Invalid canonical invoice status")

        Invoice.objects.filter(id=invoice.id).update(
            paid_amount=position["settlement"],
            status=position["status"],
        )
        invoice.paid_amount = position["settlement"]
        invoice.status = position["status"]
        return get_invoice_lifecycle(invoice, as_of=as_of)


def require_invoice_open_for_settlement(invoice):
    """Reject settlement against an invoice that has no outstanding balance."""
    position = calculate_invoice_financial_position(invoice)
    if position["outstanding"] <= Decimal("0"):
        raise ValidationError("Invoice has no outstanding balance")
    return position
