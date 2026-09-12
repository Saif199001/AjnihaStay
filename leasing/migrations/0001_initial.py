from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0011_delete_integrity"),
        ("workspaces", "0006_rls_fail_closed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Lease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agreement_number", models.CharField(blank=True, max_length=100)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("rent_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("security_deposit", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("notice_period_days", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("pending_signature", "Pending Signature"), ("active", "Active"), ("expired", "Expired"), ("terminated", "Terminated"), ("cancelled", "Cancelled")], default="draft", max_length=24)),
                ("terms", models.JSONField(blank=True, default=dict)),
                ("agreement_reference", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("terminated_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leases_created", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="leases_updated", to=settings.AUTH_USER_MODEL)),
                ("occupancy", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="lease", to="tenant.occupancy")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leases", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "status"], name="leasing_leas_workspa_9a1c2b_idx"),
                    models.Index(fields=["workspace", "start_date"], name="leasing_leas_workspa_4f7d8e_idx"),
                    models.Index(fields=["workspace", "end_date"], name="leasing_leas_workspa_6b2e5a_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="lease_end_gte_start"),
                    models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_rent_non_negative"),
                    models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_deposit_non_negative"),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE leasing_lease ENABLE ROW LEVEL SECURITY;
                ALTER TABLE leasing_lease FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_leasinglease ON leasing_lease;
                CREATE POLICY workspace_isolation_leasinglease
                    ON leasing_lease
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_leasinglease ON leasing_lease;
                ALTER TABLE leasing_lease NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE leasing_lease DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
