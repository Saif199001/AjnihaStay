from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
RLS_POLICY = f"workspace_id = {WORKSPACE_ID}"


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE payments_financialledgerentry ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE payments_financialledgerentry FORCE ROW LEVEL SECURITY")
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_financialledgerentry ON payments_financialledgerentry")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_financialledgerentry ON payments_financialledgerentry "
            f"USING ({RLS_POLICY}) WITH CHECK ({RLS_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_financialledgerentry ON payments_financialledgerentry")


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0017_final_settlement_lifecycle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[
                    ("invoice_created", "Invoice created"),
                    ("payment_recorded", "Payment recorded"),
                    ("payment_allocated", "Payment allocated"),
                    ("advance_credit_created", "Advance credit created"),
                    ("advance_credit_applied", "Advance credit applied"),
                    ("adjustment_created", "Adjustment created"),
                    ("charge_generated", "Charge generated"),
                    ("recurring_invoice_generated", "Recurring invoice generated"),
                    ("invoice_lifecycle_refreshed", "Invoice lifecycle refreshed"),
                    ("late_fee_generated", "Late fee generated"),
                    ("final_settlement_finalized", "Final settlement finalized"),
                    ("refund_requested", "Refund requested"),
                    ("refund_processing", "Refund processing"),
                    ("refund_succeeded", "Refund succeeded"),
                    ("refund_failed", "Refund failed"),
                ], max_length=40)),
                ("event_key", models.CharField(max_length=160)),
                ("occurred_at", models.DateTimeField()),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="financial_ledger_entries_created", to=settings.AUTH_USER_MODEL)),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="financial_ledger_entries", to="payments.invoice")),
                ("occupancy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="financial_ledger_entries", to="tenant.occupancy")),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="financial_ledger_entries", to="payments.payment")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="financial_ledger_entries", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "occurred_at"], name="payments_fl_workspa_4d4f8a_idx"),
                    models.Index(fields=["workspace", "event_type"], name="payments_fl_evt_type_idx"),
                    models.Index(fields=["invoice", "occurred_at"], name="payments_fl_invoice_8b2c17_idx"),
                    models.Index(fields=["payment", "occurred_at"], name="payments_fl_payment_6f0a42_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("workspace", "event_key"), name="financial_ledger_workspace_event_key_unique"),
                    models.CheckConstraint(condition=Q(amount__isnull=True) | Q(amount__gt=0), name="financial_ledger_amount_positive"),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
