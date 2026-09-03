from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Invoice, Payment
from tenant.models import Occupancy


def create_invoice(user, workspace, data):
    try:
        occupancy = Occupancy.objects.get(id=data.get("occupancy"), tenant__workspace=workspace)
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")

    return Invoice.objects.create(
        occupancy=occupancy,
        billing_start=data.get("billing_start"),
        billing_end=data.get("billing_end"),
        rent_amount=data.get("rent_amount"),
        charges_amount=data.get("charges_amount") or 0,
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

        amount = Decimal(data.get("amount"))
        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_method=data.get("payment_method"),
            payment_date=data.get("payment_date"),
            reference_id=data.get("reference_id"),
            notes=data.get("notes") or "",
        )

        total_paid = sum(existing_payment.amount for existing_payment in invoice.payments.all())
        invoice.paid_amount = total_paid
        if total_paid >= invoice.total_amount:
            invoice.status = "paid"
        elif total_paid > 0:
            invoice.status = "partial"
        else:
            invoice.status = "pending"
        invoice.save(update_fields=["paid_amount", "status"])
        return payment


def get_payments(invoice_id, workspace):
    return Payment.objects.filter(
        invoice_id=invoice_id,
        invoice__occupancy__tenant__workspace=workspace,
    ).select_related("invoice").order_by("-created_at")


def calculate_final_settlement(occupancy_id, workspace):
    try:
        occupancy = Occupancy.objects.select_related("tenant", "unit").get(
            id=occupancy_id,
            tenant__workspace=workspace,
        )
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")

    invoices = occupancy.invoices.all()
    total_rent = sum(invoice.rent_amount or 0 for invoice in invoices)
    total_charges = sum(invoice.charges_amount or 0 for invoice in invoices)
    total_paid = sum(invoice.paid_amount or 0 for invoice in invoices)
    total_amount = total_rent + total_charges
    due_amount = total_amount - total_paid
    security_deposit = occupancy.security_deposit or 0

    return {
        "tenant": occupancy.tenant.full_name,
        "unit": occupancy.unit.unit_number,
        "total_rent": total_rent,
        "total_charges": total_charges,
        "total_paid": total_paid,
        "total_due": due_amount,
        "security_deposit": security_deposit,
        "final_balance": due_amount - security_deposit,
    }
