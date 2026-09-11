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

    return Invoice.objects.create(
        occupancy=occupancy,
        billing_start=data.get("billing_start"),
        billing_end=data.get("billing_end"),
        rent_amount=rent_amount,
        charges_amount=charges_amount,
        due_date=data.get("due_date"),
    )


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
        allocation = PaymentAllocation.objects.create(
            payment=payment,
            invoice=invoice,
            amount=amount,
        )

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
            occupancy=invoice.occupancy,
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
            occupancy=invoice.occupancy,
            metadata={"allocation_id": allocation.pk},
        )
        return payment


def create_payment(user, workspace, data):
    return record_payment(user, workspace, data)


def _optional_positive_id(value, field_name):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name} ID")
    if parsed <= 0:
        raise ValidationError(f"Invalid {field_name} ID")
    return parsed


def get_payments(invoice_id, workspace):
    invoice_id = _optional_positive_id(invoice_id, "invoice")
    return Payment.objects.filter(
        invoice_id=invoice_id,
        invoice__occupancy__tenant__workspace=workspace,
    ).select_related("invoice").order_by("-created_at")


def calculate_final_settlement(occupancy_id, workspace):
    with transaction.atomic():
        try:
            occupancy = Occupancy.objects.select_for_update().select_related(
                "tenant", "unit"
            ).get(
                id=occupancy_id,
                tenant__workspace=workspace,
            )
        except Occupancy.DoesNotExist:
            raise ValidationError("Occupancy not found")

        invoices = list(occupancy.invoices.select_for_update().order_by("id"))
        total_rent = sum((invoice.rent_amount or Decimal("0") for invoice in invoices), Decimal("0"))
        total_charges = sum((invoice.charges_amount or Decimal("0") for invoice in invoices), Decimal("0"))
        total_amount = total_rent + total_charges
        total_paid = sum(
            (calculate_invoice_financial_position(invoice)["settlement"] for invoice in invoices),
            Decimal("0"),
        )
        total_due = sum(
            (calculate_invoice_financial_position(invoice)["outstanding"] for invoice in invoices),
            Decimal("0"),
        )
        security_deposit = occupancy.security_deposit or Decimal("0")

        return {
            "tenant": occupancy.tenant.full_name,
            "unit": occupancy.unit.unit_number,
            "total_rent": total_rent,
            "total_charges": total_charges,
            "total_paid": total_paid,
            "total_due": total_due,
            "security_deposit": security_deposit,
            "final_balance": total_due - security_deposit,
        }