from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
REFUND_POLICY = f"workspace_id = {WORKSPACE_ID}"


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE payments_paymentrefund ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE payments_paymentrefund FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_paymentrefund "
            "ON payments_paymentrefund"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_paymentrefund "
            "ON payments_paymentrefund "
            f"USING ({REFUND_POLICY}) WITH CHECK ({REFUND_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_paymentrefund "
            "ON payments_paymentrefund"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0012_financial_adjustment"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentRefund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("processing", "Processing"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        default="requested",
                        max_length=20,
                    ),
                ),
                ("reason", models.TextField()),
                ("reference", models.CharField(blank=True, max_length=100, null=True)),
                ("idempotency_key", models.CharField(blank=True, max_length=100, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                        to="payments.payment",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_refunds_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_refunds",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "payment"], name="payments_pr_workspa_pay_idx"),
                    models.Index(fields=["payment", "status"], name="payments_pr_payment_status_idx"),
                    models.Index(fields=["workspace", "status", "created_at"], name="payments_pr_workspa_stat_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(("amount__gt", 0)), name="payment_refund_amount_positive"),
                    models.CheckConstraint(condition=~Q(("reason", "")), name="payment_refund_reason_non_empty"),
                    models.CheckConstraint(
                        condition=Q(("status__in", ["requested", "processing", "succeeded", "failed"])),
                        name="payment_refund_status_valid",
                    ),
                    models.UniqueConstraint(
                        fields=["workspace", "idempotency_key"],
                        name="payment_refund_workspace_idempotency_key_uniq",
                    ),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
