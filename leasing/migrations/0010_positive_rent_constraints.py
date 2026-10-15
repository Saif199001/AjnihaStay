from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0009_reassert_lifecycle_relational_rls"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="lease",
            name="lease_rent_non_negative",
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.CheckConstraint(
                condition=Q(rent_amount__gt=0),
                name="lease_rent_positive",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="leaserenewal",
            name="lease_renew_rent_non_negative",
        ),
        migrations.AddConstraint(
            model_name="leaserenewal",
            constraint=models.CheckConstraint(
                condition=Q(rent_amount__gt=0),
                name="lease_renew_rent_positive",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="leasecontractversion",
            name="lease_ver_rent_non_negative",
        ),
        migrations.AddConstraint(
            model_name="leasecontractversion",
            constraint=models.CheckConstraint(
                condition=Q(rent_amount__gt=0),
                name="lease_ver_rent_positive",
            ),
        ),
    ]
