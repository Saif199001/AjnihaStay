from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "draft",
                        "pending_signature",
                        "active",
                        "expired",
                        "terminated",
                        "cancelled",
                    ]
                ),
                name="lease_status_valid",
            ),
        ),
    ]
