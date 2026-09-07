from django.db import migrations, models
import django.db.models.deletion


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
SCHEDULE_POLICY = (
    "occupancy_id IN (SELECT o.id FROM tenant_occupancy o "
    "JOIN tenant_tenant t ON t.id = o.tenant_id "
    f"WHERE t.workspace_id = {WORKSPACE_ID})"
)


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE payments_billingschedule ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE payments_billingschedule FORCE ROW LEVEL SECURITY")
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_billingschedule ON payments_billingschedule")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_billingschedule "
            "ON payments_billingschedule "
            f"USING ({SCHEDULE_POLICY}) WITH CHECK ({SCHEDULE_POLICY})"
        )


def reverse_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_billingschedule ON payments_billingschedule")


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0009_payment_allocation_rls"),
        ("tenant", "0005_alter_occupancy_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("frequency", models.CharField(choices=[("daily", "Daily"), ("monthly", "Monthly")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("next_run_date", models.DateField()),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("occupancy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_schedules", to="tenant.occupancy")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["active", "next_run_date"], name="payments_bi_active_6c4a6a_idx"),
                    models.Index(fields=["occupancy"], name="payments_bi_occupan_0f1c8f_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="billing_schedule_amount_positive"),
                ],
            },
        ),
        migrations.RunPython(apply_rls, reverse_rls),
    ]
