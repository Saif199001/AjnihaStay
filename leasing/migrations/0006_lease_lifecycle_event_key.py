from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0005_lease_contract_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaselifecycleevent",
            name="event_key",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddConstraint(
            model_name="leaselifecycleevent",
            constraint=models.UniqueConstraint(
                condition=Q(event_key__isnull=False),
                fields=("lease", "event_key"),
                name="lease_evt_lease_key_uniq",
            ),
        ),
    ]
