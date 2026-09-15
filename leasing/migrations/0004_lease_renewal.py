from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0003_lease_lifecycle_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaseRenewal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("renewal_number", models.PositiveIntegerField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("rent_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("security_deposit", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("notice_period_days", models.PositiveIntegerField(default=0)),
                ("terms", models.JSONField(blank=True, default=dict)),
                ("agreement_reference", models.CharField(blank=True, max_length=500)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")], default="draft", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_renewals_created", to=settings.AUTH_USER_MODEL)),
                ("source_lease", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="renewals", to="leasing.lease")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_renewals", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "source_lease"], name="lease_renew_ws_src_idx"),
                    models.Index(fields=["workspace", "start_date"], name="lease_renew_ws_start_idx"),
                    models.Index(fields=["workspace", "status"], name="lease_renew_ws_status_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=["source_lease", "renewal_number"], name="lease_renew_src_num_uniq"),
                    models.CheckConstraint(condition=Q(renewal_number__gte=1), name="lease_renew_num_positive"),
                    models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="lease_renew_end_gte_start"),
                    models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_renew_rent_non_negative"),
                    models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_renew_dep_non_negative"),
                    models.CheckConstraint(condition=Q(status__in=["draft", "confirmed", "cancelled"]), name="lease_renew_status_valid"),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE leasing_leaserenewal ENABLE ROW LEVEL SECURITY;
                ALTER TABLE leasing_leaserenewal FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_leasingleaserenewal ON leasing_leaserenewal;
                CREATE POLICY workspace_isolation_leasingleaserenewal
                    ON leasing_leaserenewal
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_leasingleaserenewal ON leasing_leaserenewal;
                ALTER TABLE leasing_leaserenewal NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE leasing_leaserenewal DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
