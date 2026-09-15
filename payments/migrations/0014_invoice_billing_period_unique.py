from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0013_payment_refund"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.UniqueConstraint(
                fields=["occupancy", "billing_start", "billing_end"],
                name="invoice_occupancy_billing_period_uniq",
            ),
        ),
    ]
