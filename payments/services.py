from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Invoice, Payment
from tenant.models import Occupancy


def create_invoice(user, workspace, data):
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


def create_payment(user, workspace, data):
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

        total_paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        outstanding = invoice.total_amount - total_paid
        if amount > outstanding:
            raise ValidationError("Payment exceeds remaining amount")

        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_method=data.get("payment_method"),
            payment_date=data.get("payment_date"),
            reference_id=data.get("reference_id"),
            notes=data.get("notes") or "",
        )

        total_paid += amount
        invoice.paid_amount = total_paid
        if total_paid == invoice.total_amount:
            invoice.status = "paid"
        elif total_paid > 0:
            invoice.status = "partial"
        else:
            invoice.status = "pending"
        invoice.save(update_fields=["paid_amount", "status"])
        return payment


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

        invoices = list(
            occupancy.invoices.select_for_update().order_by("id")
        )
        total_rent = sum(
            (invoice.rent_amount or Decimal("0") for invoice in invoices),
            Decimal("0"),
        )
        total_charges = sum(
            (invoice.charges_amount or Decimal("0") for invoice in invoices),
            Decimal("0"),
        )
        total_amount = total_rent + total_charges

        payment_totals = Payment.objects.filter(
            invoice__occupancy=occupancy,
        ).aggregate(total=Sum("amount"))
        total_paid = payment_totals["total"] or Decimal("0")
        total_due = max(total_amount - total_paid, Decimal("0"))
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
