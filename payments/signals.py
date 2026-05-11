from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import Payment


@receiver(post_save, sender=Payment)
def update_invoice_status(sender, instance, **kwargs):

    invoice = instance.invoice

    total_paid = invoice.payments.aggregate(
        total=Sum("amount")
    )["total"] or 0

    invoice.paid_amount = total_paid

    if total_paid >= invoice.total_amount:
        invoice.status = "paid"
    elif total_paid > 0:
        invoice.status = "partial"
    else:
        invoice.status = "pending"

    invoice.save()