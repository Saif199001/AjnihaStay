from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0016_late_fee_engine"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinalSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_rent", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_charges", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_paid", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_due", models.DecimalField(decimal_places=2, max_digits=10)),
                ("security_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("retained_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("refundable_deposit", models.DecimalField(decimal_places=2, max_digits=10)),
                ("final_balance", models.DecimalField(decimal_places=2, max_digits=10)),
                ("outcome", models.CharField(choices=[("no_deposit", "No deposit"), ("full_refund", "Full refund"), ("partial_refund", "Partial refund"), ("full_retention", "Full retention")], max_length=30)),
                ("settled_at", models.DateTimeField(auto_now_add=True)),
                ("occupancy", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="final_settlement", to="tenant.occupancy")),
                ("settled_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="final_settlements_created", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="final_settlements", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "settled_at"], name="payments_fs_workspa_6c0f9d_idx"),
                    models.Index(fields=["workspace", "outcome"], name="payments_fs_workspa_8b7a22_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(("total_rent__gte", 0)), name="final_settlement_rent_non_negative"),
                    models.CheckConstraint(condition=Q(("total_charges__gte", 0)), name="final_settlement_charges_non_negative"),
                    models.CheckConstraint(condition=Q(("total_paid__gte", 0)), name="final_settlement_paid_non_negative"),
                    models.CheckConstraint(condition=Q(("total_due__gte", 0)), name="final_settlement_due_non_negative"),
                    models.CheckConstraint(condition=Q(("security_deposit__gte", 0)), name="final_settlement_deposit_non_negative"),
                    models.CheckConstraint(condition=Q(("retained_deposit__gte", 0)), name="final_settlement_retained_non_negative"),
                    models.CheckConstraint(condition=Q(("refundable_deposit__gte", 0)), name="final_settlement_refundable_non_negative"),
                ],
            },
        ),
    ]
