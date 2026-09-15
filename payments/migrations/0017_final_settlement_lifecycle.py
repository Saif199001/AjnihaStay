from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
RLS_POLICY = f"workspace_id = {WORKSPACE_ID}"


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE payments_finalsettlement ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE payments_finalsettlement FORCE ROW LEVEL SECURITY")
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_finalsettlement ON payments_finalsettlement")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_finalsettlement ON payments_finalsettlement "
            f"USING ({RLS_POLICY}) WITH CHECK ({RLS_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_finalsettlement ON payments_finalsettlement")


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0016_late_fee_engine"),
        ("workspaces", "0006_rls_fail_closed"),
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
                ("settled_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="final_settlements_created", to="accounts.user")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="final_settlements", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "settled_at"], name="payments_fs_workspa_6c0f9d_idx"),
                    models.Index(fields=["workspace", "outcome"], name="payments_fs_workspa_8b7a22_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(total_rent__gte=0), name="final_settlement_rent_non_negative"),
                    models.CheckConstraint(condition=Q(total_charges__gte=0), name="final_settlement_charges_non_negative"),
                    models.CheckConstraint(condition=Q(total_paid__gte=0), name="final_settlement_paid_non_negative"),
                    models.CheckConstraint(condition=Q(total_due__gte=0), name="final_settlement_due_non_negative"),
                    models.CheckConstraint(condition=Q(security_deposit__gte=0), name="final_settlement_deposit_non_negative"),
                    models.CheckConstraint(condition=Q(retained_deposit__gte=0), name="final_settlement_retained_non_negative"),
                    models.CheckConstraint(condition=Q(refundable_deposit__gte=0), name="final_settlement_refundable_non_negative"),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
