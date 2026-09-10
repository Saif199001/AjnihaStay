from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0015_financial_adjustment_hardening"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LateFeePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("grace_period_days", models.PositiveIntegerField(default=0)),
                ("calculation_mode", models.CharField(choices=[("fixed", "Fixed"), ("percentage", "Percentage")], default="fixed", max_length=20)),
                ("rate", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("minimum_overdue_balance", models.DecimalField(decimal_places=2, default=Decimal("0.01"), max_digits=10)),
                ("maximum_late_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="late_fee_policy", to="workspaces.workspace")),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=Q(("grace_period_days__gte", 0)), name="late_fee_grace_non_negative"),
                    models.CheckConstraint(condition=Q(("rate__gte", 0)), name="late_fee_rate_non_negative"),
                    models.CheckConstraint(condition=Q(("minimum_overdue_balance__gt", 0)), name="late_fee_min_balance_positive"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LateFee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("outstanding_balance", models.DecimalField(decimal_places=2, max_digits=10)),
                ("calculation_mode", models.CharField(choices=[("fixed", "Fixed"), ("percentage", "Percentage")], max_length=20)),
                ("reason", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="late_fees_created", to=settings.AUTH_USER_MODEL)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="late_fees", to="payments.invoice")),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="late_fees", to="payments.latefeepolicy")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="late_fees", to="workspaces.workspace")),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=Q(("amount__gt", 0)), name="late_fee_amount_positive"),
                    models.CheckConstraint(condition=Q(("outstanding_balance__gt", 0)), name="late_fee_balance_positive"),
                    models.UniqueConstraint(fields=("workspace", "invoice", "policy", "effective_date"), name="late_fee_invoice_policy_date_unique"),
                ],
                "indexes": [
                    models.Index(fields=["workspace", "invoice"], name="payments_la_workspa_e9c494_idx"),
                    models.Index(fields=["invoice", "effective_date"], name="payments_la_invoice_64290e_idx"),
                ],
            },
        ),
    ]
