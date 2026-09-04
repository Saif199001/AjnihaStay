from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("unit", "0004_unit_amenities"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.CheckConstraint(
                condition=Q(capacity__gte=1),
                name="unit_capacity_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.CheckConstraint(
                condition=Q(rent__isnull=True) | Q(rent__gte=0),
                name="unit_rent_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="subunit",
            constraint=models.CheckConstraint(
                condition=Q(rent__gte=0),
                name="subunit_rent_non_negative",
            ),
        ),
    ]
