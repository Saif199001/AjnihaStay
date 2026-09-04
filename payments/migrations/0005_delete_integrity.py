from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_financial_integrity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="occupancy",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="invoices",
                to="tenant.occupancy",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="invoice",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="payments",
                to="payments.invoice",
            ),
        ),
    ]
