from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from .models import Payment, Invoice

@receiver(post_save, sender=Payment)
def update_invoice_status(sender, instance, **kwargs):

    invoice = instance.invoice

    total_paid = invoice.payments.aggregate(
        total=models.Sum("amount")
    )["total"] or 0

    status = "pending"

    if total_paid >= invoice.total_amount:
        status = "paid"

    elif total_paid > 0:
        status = "partial"

    Invoice.objects.filter(
        id=invoice.id
    ).update(
        paid_amount=total_paid,
        status=status
    )


@receiver(post_delete, sender=Payment)
def recalculate_invoice_on_delete(
    sender,
    instance,
    **kwargs
):

    invoice = instance.invoice

    total_paid = invoice.payments.aggregate(
        total=models.Sum("amount")
    )["total"] or 0

    status = "pending"

    if total_paid >= invoice.total_amount:
        status = "paid"

    elif total_paid > 0:
        status = "partial"

    Invoice.objects.filter(
        id=invoice.id
    ).update(
        paid_amount=total_paid,
        status=status
    )