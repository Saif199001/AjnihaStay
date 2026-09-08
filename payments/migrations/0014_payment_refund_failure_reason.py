from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0013_payment_refund"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentrefund",
            name="failure_reason",
            field=models.TextField(blank=True, default=""),
        ),
    ]
