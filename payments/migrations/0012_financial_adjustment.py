from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
ADJUSTMENT_POLICY = f"workspace_id = {WORKSPACE_ID}"


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE payments_financialadjustment ENABLE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "ALTER TABLE payments_financialadjustment FORCE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_financialadjustment "
            "ON payments_financialadjustment"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_financialadjustment "
            "ON payments_financialadjustment "
            f"USING ({ADJUSTMENT_POLICY}) WITH CHECK ({ADJUSTMENT_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_financialadjustment "
            "ON payments_financialadjustment"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0011_advance_credit"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialAdjustment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "adjustment_type",
                    models.CharField(
                        choices=[
                            ("credit", "Credit"),
                            ("debit", "Debit"),
                            ("discount", "Discount"),
                            ("waiver", "Waiver"),
                            ("write_off", "Write-off"),
                        ],
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("reason", models.TextField()),
                ("reference", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "idempotency_key",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_adjustments_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_adjustments",
                        to="payments.invoice",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_adjustments",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["workspace", "invoice"],
                        name="payments_fa_workspa_6e1c6d_idx",
                    ),
                    models.Index(
                        fields=["workspace", "adjustment_type", "created_at"],
                        name="payments_fa_workspa_9e9d8c_idx",
                    ),
                    models.Index(
                        fields=["invoice", "created_at"],
                        name="payments_fa_invoice_4cfd1d_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("amount__gt", 0)),
                        name="financial_adjustment_amount_positive",
                    ),
                    models.CheckConstraint(
                        condition=Q(
                            ("adjustment_type__in", [
                                "credit",
                                "debit",
                                "discount",
                                "waiver",
                                "write_off",
                            ])
                        ),
                        name="financial_adjustment_type_valid",
                    ),
                    models.CheckConstraint(
                        condition=~Q(("reason", "")),
                        name="financial_adjustment_reason_non_empty",
                    ),
                    models.UniqueConstraint(
                        fields=["workspace", "idempotency_key"],
                        name="financial_adjustment_workspace_idempotency_key_uniq",
                    ),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
