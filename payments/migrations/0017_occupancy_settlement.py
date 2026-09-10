from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0016_late_fee_engine"),
        ("tenant", "0010_occupancy_billing_type_and_cycle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OccupancySettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(default="settled", max_length=20)),
                ("outcome", models.CharField(choices=[("no_deposit", "No deposit"), ("full_refund", "Full refund"), ("partial_refund", "Partial refund"), ("full_retention", "Full retention")], max_length=30)),
                ("invoice_outstanding", models.DecimalField(decimal_places=2, max_digits=10)),
                ("security_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("refundable_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("retained_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("settled_at", models.DateTimeField(auto_now_add=True)),
                ("occupancy", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="settlement", to="tenant.occupancy")),
                ("settled_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="occupancy_settlements_created", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="occupancy_settlements", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "settled_at"], name="payments_os_workspa_settled_idx"),
                    models.Index(fields=["occupancy"], name="payments_os_occupancy_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(("invoice_outstanding", 0)), name="settlement_outstanding_zero"),
                    models.CheckConstraint(condition=Q(("security_deposit__gte", 0)), name="settlement_deposit_non_negative"),
                    models.CheckConstraint(condition=Q(("refundable_deposit__gte", 0)), name="settlement_refundable_non_negative"),
                    models.CheckConstraint(condition=Q(("retained_deposit__gte", 0)), name="settlement_retained_non_negative"),
                ],
            },
        ),
    ]
