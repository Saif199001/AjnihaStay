from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0002_lease_status_constraint"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaseLifecycleEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("created", "Created"), ("pending_signature", "Pending Signature"), ("activated", "Activated"), ("renewed", "Renewed"), ("notice", "Notice"), ("expired", "Expired"), ("terminated", "Terminated"), ("cancelled", "Cancelled")], max_length=24)),
                ("occurred_at", models.DateTimeField()),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="lease_lifecycle_events", to=settings.AUTH_USER_MODEL)),
                ("lease", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lifecycle_events", to="leasing.lease")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_lifecycle_events", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "lease"], name="lease_evt_ws_lease_idx"),
                    models.Index(fields=["workspace", "event_type"], name="lease_evt_ws_type_idx"),
                    models.Index(fields=["lease", "occurred_at"], name="lease_evt_lease_time_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(event_type__in=["created", "pending_signature", "activated", "renewed", "notice", "expired", "terminated", "cancelled"]), name="lease_evt_type_valid"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LeaseNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notice_date", models.DateField()),
                ("effective_date", models.DateField()),
                ("notice_type", models.CharField(choices=[("termination", "Termination"), ("non_renewal", "Non Renewal"), ("other", "Other")], max_length=20)),
                ("reason", models.CharField(max_length=500)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("issued", "Issued"), ("withdrawn", "Withdrawn"), ("effective", "Effective"), ("completed", "Completed")], default="draft", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_notices_created", to=settings.AUTH_USER_MODEL)),
                ("lease", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notices", to="leasing.lease")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_notices", to="workspaces.workspace")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["workspace", "lease"], name="lease_note_ws_lease_idx"),
                    models.Index(fields=["workspace", "effective_date"], name="lease_note_ws_eff_idx"),
                    models.Index(fields=["workspace", "status"], name="lease_note_ws_status_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(effective_date__gte=models.F("notice_date")), name="lease_note_eff_gte_notice"),
                    models.CheckConstraint(condition=Q(status__in=["draft", "issued", "withdrawn", "effective", "completed"]), name="lease_note_status_valid"),
                    models.CheckConstraint(condition=Q(notice_type__in=["termination", "non_renewal", "other"]), name="lease_note_type_valid"),
                ],
            },
        ),
        migrations.RunSQL(
            sql="ALTER TABLE leasing_leaselifecycleevent ENABLE ROW LEVEL SECURITY; ALTER TABLE leasing_leaselifecycleevent FORCE ROW LEVEL SECURITY; CREATE POLICY workspace_isolation_leaselifecycleevent ON leasing_leaselifecycleevent USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint);",
            reverse_sql="DROP POLICY IF EXISTS workspace_isolation_leaselifecycleevent ON leasing_leaselifecycleevent; ALTER TABLE leasing_leaselifecycleevent NO FORCE ROW LEVEL SECURITY; ALTER TABLE leasing_leaselifecycleevent DISABLE ROW LEVEL SECURITY;",
        ),
        migrations.RunSQL(
            sql="ALTER TABLE leasing_leasenotice ENABLE ROW LEVEL SECURITY; ALTER TABLE leasing_leasenotice FORCE ROW LEVEL SECURITY; CREATE POLICY workspace_isolation_leasenotice ON leasing_leasenotice USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint);",
            reverse_sql="DROP POLICY IF EXISTS workspace_isolation_leasenotice ON leasing_leasenotice; ALTER TABLE leasing_leasenotice NO FORCE ROW LEVEL SECURITY; ALTER TABLE leasing_leasenotice DISABLE ROW LEVEL SECURITY;",
        ),
    ]
