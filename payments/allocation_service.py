from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Invoice, Payment, PaymentAllocation


def _decimal_amount(value):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid allocation amount")
    if amount <= 0:
        raise ValidationError("Allocation amount must be greater than zero")
    return amount


def _normalize_allocations(allocations):
    if not allocations:
        raise ValidationError("At least one invoice allocation is required")

    normalized = []
    seen = set()
    for item in allocations:
        invoice_value = item.get("invoice")
        invoice_id = getattr(invoice_value, "id", invoice_value)
        try:
            invoice_id = int(invoice_id)
        except (TypeError, ValueError):
            raise ValidationError("Invalid invoice ID")
        if invoice_id <= 0:
            raise ValidationError("Invalid invoice ID")
        if invoice_id in seen:
            raise ValidationError("An invoice may only appear once in an allocation request")
        seen.add(invoice_id)
        normalized.append((invoice_id, _decimal_amount(item.get("amount"))))
    return normalized


def _recalculate_invoice_state_from_allocations(invoice):
    total_paid = (
        invoice.allocations.aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    total_amount = invoice.total_amount or Decimal("0")
    if total_paid == total_amount:
        status = "paid"
    elif total_paid > 0:
        status = "partial"
    else:
        status = "pending"

    Invoice.objects.filter(id=invoice.id).update(
        paid_amount=total_paid,
        status=status,
    )
    invoice.paid_amount = total_paid
    invoice.status = status
    return invoice


def allocate_payment(user, workspace, payment, allocations):
    """Atomically allocate one payment across one or more invoices."""
    normalized = _normalize_allocations(allocations)

    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(
                id=getattr(payment, "id", payment),
                workspace=workspace,
            )
        except Payment.DoesNotExist:
            raise ValidationError("Payment not found")

        invoice_ids = sorted(invoice_id for invoice_id, _ in normalized)
        invoices = list(
            Invoice.objects.select_for_update()
            .select_related("occupancy__tenant")
            .filter(id__in=invoice_ids, occupancy__tenant__workspace=workspace)
            .order_by("id")
        )
        if len(invoices) != len(invoice_ids):
            raise ValidationError("One or more invoices were not found")
        invoices_by_id = {invoice.id: invoice for invoice in invoices}

        already_allocated = (
            PaymentAllocation.objects.filter(payment=payment)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        requested_total = sum(
            (amount for _, amount in normalized), Decimal("0")
        )
        if already_allocated + requested_total > payment.amount:
            raise ValidationError("Allocation exceeds payment amount")

        for invoice_id, amount in normalized:
            invoice = invoices_by_id[invoice_id]
            allocated_to_invoice = (
                PaymentAllocation.objects.filter(invoice=invoice)
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0")
            )
            outstanding = (invoice.total_amount or Decimal("0")) - allocated_to_invoice
            if amount > outstanding:
                raise ValidationError("Allocation exceeds invoice remaining amount")

        created = []
        for invoice_id, amount in normalized:
            created.append(
                PaymentAllocation.objects.create(
                    payment=payment,
                    invoice=invoices_by_id[invoice_id],
                    amount=amount,
                )
            )

        for invoice in invoices:
            _recalculate_invoice_state_from_allocations(invoice)

        return created
