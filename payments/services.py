from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from .adjustment_service import calculate_invoice_financial_position
from .authorization import require_mutation_permission
from .ledger_service import post_ledger_event
from .models import AdvanceCredit, Invoice, Payment, PaymentAllocation
from tenant.models import Occupancy


def create_invoice(user, workspace, data):
    require_mutation_permission(user, workspace)
    try:
        occupancy = Occupancy.objects.get(id=data.get("occupancy"), tenant__workspace=workspace)
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")

    try:
        rent_amount = Decimal(data.get("rent_amount"))
        charges_amount = Decimal(data.get("charges_amount") or 0)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid invoice amount")

    if rent_amount < 0 or charges_amount < 0:
        raise ValidationError("Invoice amounts cannot be negative")

    ledger_event_type = data.get("ledger_event_type", "invoice_created")
    ledger_event_key = data.get("ledger_event_key")
    ledger_metadata = data.get("ledger_metadata") or {}
    allowed_ledger_event_types = {"invoice_created", "recurring_invoice_generated"}
    if ledger_event_type not in allowed_ledger_event_types:
        raise ValidationError("Invalid invoice ledger event type")
    if ledger_event_type == "invoice_created":
        ledger_event_key = ledger_event_key or None
    else:
        if not ledger_event_key:
            raise ValidationError("Recurring invoice ledger event key is required")

    with transaction.atomic():
        invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=data.get("billing_start"),
            billing_end=data.get("billing_end"),
            rent_amount=rent_amount,
            charges_amount=charges_amount,
            due_date=data.get("due_date"),
        )
        post_ledger_event(
            user,
            workspace,
            event_type=ledger_event_type,
            event_key=ledger_event_key or f"invoice:{invoice.pk}:created",
            occurred_at=invoice.created_at,
            amount=invoice.total_amount,
            invoice=invoice,
            occupancy=occupancy,
            metadata={"invoice_number": invoice.invoice_number, **ledger_metadata},
        )
        return invoice


def get_invoices(workspace):
    return Invoice.objects.filter(
        occupancy__tenant__workspace=workspace
    ).select_related("occupancy", "occupancy__tenant")


def get_invoice(invoice_id, workspace):
    try:
        return Invoice.objects.get(id=invoice_id, occupancy__tenant__workspace=workspace)
    except Invoice.DoesNotExist:
        raise ValidationError("Invoice not found")


def get_invoice_allocated_amount(invoice):
    return (
        PaymentAllocation.objects.filter(invoice=invoice)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


def get_invoice_credit_applied_amount(invoice):
    return (
        invoice.advance_credit_applications.aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


def get_invoice_settled_amount(invoice):
    return get_invoice_allocated_amount(invoice) + get_invoice_credit_applied_amount(invoice)


def get_payment_reserved_credit_amount(payment):
    return (
        AdvanceCredit.objects.filter(source_payment=payment)
        .aggregate(total=Sum("original_amount"))["total"]
        or Decimal("0")
    )


def get_payment_available_allocation_amount(payment):
    allocated = (
        PaymentAllocation.objects.filter(payment=payment)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    reserved_credit = get_payment_reserved_credit_amount(payment)
    return max(payment.amount - allocated - reserved_credit, Decimal("0"))


def recalculate_invoice_state(invoice):
    position = calculate_invoice_financial_position(invoice)
    Invoice.objects.filter(id=invoice.id).update(
        paid_amount=position["settlement"],
        status=position["status"],
    )
    invoice.paid_amount = position["settlement"]
    invoice.status = position["status"]
    return invoice


def record_payment(user, workspace, data):
    require_mutation_permission(user, workspace)
    with transaction.atomic():
        invoice_value = data.get("invoice")
        invoice_id = getattr(invoice_value, "id", invoice_value)
        try:
            invoice = Invoice.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(id=invoice_id, occupancy__tenant__workspace=workspace)
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        try:
            amount = Decimal(data.get("amount"))
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError("Invalid payment amount")

        if amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")

        position = calculate_invoice_financial_position(invoice)
        if amount > position["outstanding"]:
            raise ValidationError("Payment exceeds remaining amount")

        payment = Payment.objects.create(
            workspace=workspace,
            invoice=invoice,
            amount=amount,
            payment_method=data.get("payment_method"),
            payment_date=data.get("payment_date"),
            reference_id=data.get("reference_id"),
            notes=data.get("notes") or "",
        )
        allocation = PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=amount)

        recalculate_invoice_state(invoice)

        post_ledger_event(
            user,
            workspace,
            event_type="payment_recorded",
            event_key=f"payment:{payment.pk}:recorded",
            occurred_at=payment.created_at,
            amount=payment.amount,
            invoice=invoice,
            payment=payment,
            metadata={"payment_id": payment.pk},
        )
        post_ledger_event(
            user,
            workspace,
            event_type="payment_allocated",
            event_key=f"payment-allocation:{allocation.pk}:created",
            occurred_at=payment.created_at,
            amount=allocation.amount,
            invoice=invoice,
            payment=payment,
            metadata={"allocation_id": allocation.pk},
        )
        return payment


def create_payment(user, workspace, data):
    return record_payment(user, workspace, data)
