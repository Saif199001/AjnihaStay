from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(rent_amount__gte=0),
                name="invoice_rent_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(charges_amount__gte=0),
                name="invoice_charges_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(paid_amount__gte=0),
                name="invoice_paid_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(total_amount__isnull=True) | Q(total_amount__gte=0),
                name="invoice_total_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(total_amount__isnull=True) | Q(paid_amount__lte=F("total_amount")),
                name="invoice_paid_lte_total",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
        ),
    ]
