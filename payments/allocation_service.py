from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .adjustment_service import calculate_invoice_financial_position
from .authorization import require_mutation_permission
from .models import Invoice, Payment, PaymentAllocation
from .services import get_payment_available_allocation_amount


def _decimal_amount(value):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid allocation amount")
    if not amount.is_finite():
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
        if not isinstance(item, dict):
            raise ValidationError("Invalid allocation entry")
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
    """Reconcile compatibility invoice state from canonical financial position."""
    position = calculate_invoice_financial_position(invoice)
    Invoice.objects.filter(id=invoice.id).update(paid_amount=position["settlement"], status=position["status"])
    invoice.paid_amount = position["settlement"]
    invoice.status = position["status"]
    return invoice


def allocate_payment(user, workspace, payment, allocations):
    """Atomically allocate one payment across one or more invoices."""
    require_mutation_permission(user, workspace)
    normalized = _normalize_allocations(allocations)

    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(
                id=getattr(payment, "id", payment), workspace=workspace
            )
        except Payment.DoesNotExist:
            raise ValidationError("Payment not found")

        invoice_ids = sorted(invoice_id for invoice_id, _ in normalized)
        invoices = list(
            Invoice.objects.select_for_update().select_related("occupancy__tenant")
            .filter(id__in=invoice_ids, occupancy__tenant__workspace=workspace).order_by("id")
        )
        if len(invoices) != len(invoice_ids):
            raise ValidationError("One or more invoices were not found")
        invoices_by_id = {invoice.id: invoice for invoice in invoices}

        if payment.invoice_id and any(invoice_id != payment.invoice_id for invoice_id, _ in normalized):
            raise ValidationError("A legacy invoice-linked payment can only be allocated to its linked invoice")
        requested_total = sum((amount for _, amount in normalized), Decimal("0"))
        available_capacity = get_payment_available_allocation_amount(payment)
        if requested_total > available_capacity:
            raise ValidationError("Allocation exceeds payment amount")
        for invoice_id, amount in normalized:
            invoice = invoices_by_id[invoice_id]
            position = calculate_invoice_financial_position(invoice)
            if amount > position["outstanding"]:
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

        from .ledger_service import post_ledger_event
        for allocation in created:
            post_ledger_event(
                user,
                workspace,
                event_type="payment_allocated",
                event_key=f"payment-allocation:{allocation.pk}:created",
                occurred_at=allocation.created_at,
                amount=allocation.amount,
                invoice=allocation.invoice,
                payment=payment,
                occupancy=allocation.invoice.occupancy,
                metadata={"allocation_id": allocation.pk},
            )
        return created
