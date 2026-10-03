from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0012_charge_billing_schedule"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="occupancy",
            name="occupancy_rent_non_negative",
        ),
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.CheckConstraint(
                condition=Q(rent__gt=0),
                name="occupancy_rent_positive",
            ),
        ),
    ]
