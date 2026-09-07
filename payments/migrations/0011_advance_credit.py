from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
ADVANCE_CREDIT_POLICY = f"workspace_id = {WORKSPACE_ID}"
ADVANCE_CREDIT_APPLICATION_POLICY = (
    f"credit_id IN (SELECT ac.id FROM payments_advancecredit ac "
    f"WHERE ac.workspace_id = {WORKSPACE_ID}) "
    f"AND invoice_id IN (SELECT i.id FROM payments_invoice i "
    f"JOIN tenant_occupancy o ON o.id = i.occupancy_id "
    f"JOIN tenant_tenant t ON t.id = o.tenant_id "
    f"WHERE t.workspace_id = {WORKSPACE_ID})"
)


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE payments_advancecredit ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE payments_advancecredit FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_advancecredit "
            "ON payments_advancecredit"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_advancecredit "
            "ON payments_advancecredit "
            f"USING ({ADVANCE_CREDIT_POLICY}) WITH CHECK ({ADVANCE_CREDIT_POLICY})"
        )

        cursor.execute(
            "ALTER TABLE payments_advancecreditapplication ENABLE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "ALTER TABLE payments_advancecreditapplication FORCE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_advancecreditapplication "
            "ON payments_advancecreditapplication"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_advancecreditapplication "
            "ON payments_advancecreditapplication "
            f"USING ({ADVANCE_CREDIT_APPLICATION_POLICY}) "
            f"WITH CHECK ({ADVANCE_CREDIT_APPLICATION_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_advancecreditapplication "
            "ON payments_advancecreditapplication"
        )
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_advancecredit "
            "ON payments_advancecredit"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0010_billing_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdvanceCredit",
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
                ("original_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "occupancy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advance_credits",
                        to="tenant.occupancy",
                    ),
                ),
                (
                    "source_payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advance_credit",
                        to="payments.payment",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advance_credits",
                        to="tenant.tenant",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advance_credits",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["workspace", "tenant"],
                        name="payments_ad_workspa_5cd464_idx",
                    ),
                    models.Index(
                        fields=["tenant", "created_at"],
                        name="payments_ad_tenant_85ab7f_idx",
                    ),
                    models.Index(
                        fields=["occupancy"],
                        name="payments_ad_occupan_17e7f8_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("original_amount__gt", 0)),
                        name="advance_credit_amount_positive",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AdvanceCreditApplication",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "credit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="applications",
                        to="payments.advancecredit",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advance_credit_applications",
                        to="payments.invoice",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["credit"],
                        name="payments_ad_credit_fdc584_idx",
                    ),
                    models.Index(
                        fields=["invoice"],
                        name="payments_ad_invoice_ec31dc_idx",
                    ),
                    models.Index(
                        fields=["invoice", "created_at"],
                        name="payments_ad_invoice_a2fe64_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("amount__gt", 0)),
                        name="advance_credit_application_amount_positive",
                    ),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
