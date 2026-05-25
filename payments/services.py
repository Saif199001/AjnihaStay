from .models import Invoice, Payment
from decimal import Decimal
from tenant.models import Occupancy
from django.db import transaction
from django.core.exceptions import ValidationError


# 🔥 CREATE INVOICE
def create_invoice(user, data):

    try:
        occupancy = Occupancy.objects.get(id=data.get("occupancy"))
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")

    if occupancy.tenant.owner != user:
        raise ValidationError("Unauthorized")

    return Invoice.objects.create(
        occupancy=occupancy,
        billing_start=data.get("billing_start"),
        billing_end=data.get("billing_end"),
        rent_amount=data.get("rent_amount"),
        charges_amount=data.get("charges_amount") or 0,
        due_date=data.get("due_date"),
    )


# 🔥 GET ALL INVOICES (OWNER BASED)
def get_invoices(user):

    return Invoice.objects.filter(
        occupancy__tenant__owner=user
    ).select_related("occupancy", "occupancy__tenant")


# 🔥 GET SINGLE INVOICE
def get_invoice(invoice_id, user):

    try:
        return Invoice.objects.get(
            id=invoice_id,
            occupancy__tenant__owner=user
        )
    except Invoice.DoesNotExist:
        raise ValidationError("Invoice not found")


# 🔥 CREATE PAYMENT
def create_payment(user, data):

    with transaction.atomic():

        try:
            invoice = Invoice.objects.get(id=data.get("invoice"))
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        if invoice.occupancy.tenant.owner != user:
            raise ValidationError("Unauthorized")

        payment = Payment.objects.create(
            invoice=invoice,
            amount=data.get("amount"),
            payment_method=data.get("payment_method"),
            payment_date=data.get("payment_date"),
            reference_id=data.get("reference_id"),
            notes=data.get("notes"),
        )

        return payment


# 🔥 GET PAYMENTS (BY INVOICE)
def get_payments(invoice_id, user):

    return Payment.objects.filter(
        invoice_id=invoice_id,
        invoice__occupancy__tenant__owner=user
    ).select_related("invoice").order_by("-created_at")


def calculate_final_settlement( occupancy_id, user ):

    try:

        occupancy = Occupancy.objects.get(
            id=occupancy_id
        )

    except Occupancy.DoesNotExist:

        raise ValidationError(
            "Occupancy not found"
        )

    # 🔐 SECURITY CHECK
    if occupancy.tenant.owner != user:

        raise ValidationError(
            "Unauthorized"
        )

    invoices = occupancy.invoices.all()

    total_rent = sum(
        invoice.rent_amount or 0
        for invoice in invoices
    )

    total_charges = sum(
        invoice.charges_amount or 0
        for invoice in invoices
    )

    total_paid = sum(
        invoice.paid_amount or 0
        for invoice in invoices
    )

    total_amount = (
        total_rent +
        total_charges
    )

    due_amount = (
        total_amount -
        total_paid
    )

    security_deposit = (
        occupancy.security_deposit or 0
    )

    final_balance = (
        due_amount -
        security_deposit
    )

    return {

        "tenant": occupancy.tenant.full_name,

        "unit": occupancy.unit.unit_number,

        "total_rent": total_rent,

        "total_charges": total_charges,

        "total_paid": total_paid,

        "total_due": due_amount,

        "security_deposit": security_deposit,

        "final_balance": final_balance,
    }