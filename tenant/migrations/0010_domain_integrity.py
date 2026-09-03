from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0009_alter_tenant_profile_photo"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.CheckConstraint(
                condition=Q(rent__gte=0),
                name="occupancy_rent_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.CheckConstraint(
                condition=Q(security_deposit__gte=0),
                name="occupancy_deposit_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.CheckConstraint(
                condition=Q(check_out_date__isnull=True) | Q(check_out_date__gte=F("check_in_date")),
                name="occupancy_checkout_gte_checkin",
            ),
        ),
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.CheckConstraint(
                condition=Q(next_due_date__gte=F("check_in_date")),
                name="occupancy_next_due_gte_checkin",
            ),
        ),
        migrations.AddConstraint(
            model_name="charge",
            constraint=models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="charge_amount_positive",
            ),
        ),
    ]
