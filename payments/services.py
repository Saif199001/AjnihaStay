from .models import Invoice, Payment
from django.core.exceptions import ValidationError


# 🔥 CREATE INVOICE
def create_invoice(data):

    invoice = Invoice.objects.create(
        occupancy_id=data.get("occupancy"),
        billing_start=data.get("billing_start"),
        billing_end=data.get("billing_end"),
        rent_amount=data.get("rent_amount"),
        charges_amount=data.get("charges_amount") or 0,
        due_date=data.get("due_date"),
    )

    return invoice


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
def create_payment(data):

    payment = Payment.objects.create(
        invoice_id=data.get("invoice"),
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
    ).select_related("invoice")