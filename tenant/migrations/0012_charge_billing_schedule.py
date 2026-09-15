from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0011_delete_integrity"),
        ("payments", "0010_billing_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="charge",
            name="billing_schedule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="charges",
                to="payments.billingschedule",
            ),
        ),
        migrations.AddConstraint(
            model_name="charge",
            constraint=models.UniqueConstraint(
                condition=Q(("billing_schedule__isnull", False)),
                fields=("billing_schedule", "charge_date"),
                name="charge_schedule_date_unique",
            ),
        ),
    ]
