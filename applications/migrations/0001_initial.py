from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workspaces", "0001_initial"),
        ("properties", "0006_property_owner_delete_integrity"),
        ("unit", "0005_capacity_rent_integrity"),
    ]
    operations = [
        migrations.CreateModel(name="Applicant", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("full_name", models.CharField(max_length=200)), ("phone", models.CharField(max_length=15)),
            ("email", models.EmailField(blank=True, max_length=254, null=True)), ("address", models.TextField(blank=True, default="")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applicants", to="workspaces.workspace")),
        ], options={"indexes": [models.Index(fields=["workspace", "created_at"], name="applications_applicant_workspace_created_idx"), models.Index(fields=["workspace", "phone"], name="applications_applicant_workspace_phone_idx")]}),
        migrations.CreateModel(name="Application", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("requested_check_in_date", models.DateField(blank=True, null=True)), ("requested_check_out_date", models.DateField(blank=True, null=True)),
            ("status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("under_review", "Under review"), ("approved", "Approved"), ("rejected", "Rejected"), ("withdrawn", "Withdrawn")], default="draft", max_length=20)),
            ("submitted_at", models.DateTimeField(blank=True, null=True)), ("reviewed_at", models.DateTimeField(blank=True, null=True)), ("decided_at", models.DateTimeField(blank=True, null=True)),
            ("rejection_reason", models.TextField(blank=True, default="")), ("withdrawal_reason", models.TextField(blank=True, default="")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("applicant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="applications.applicant")),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_applications", to=settings.AUTH_USER_MODEL)),
            ("property", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="properties.property")),
            ("subunit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="unit.subunit")),
            ("unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="unit.unit")),
            ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_applications", to=settings.AUTH_USER_MODEL)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="workspaces.workspace")),
        ], options={"indexes": [models.Index(fields=["workspace", "status", "created_at"], name="applications_application_workspace_status_created_idx"), models.Index(fields=["workspace", "applicant", "property", "status"], name="applications_application_workspace_applicant_property_status_idx")]}),
        migrations.CreateModel(name="ApplicationEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("from_status", models.CharField(max_length=20)), ("to_status", models.CharField(max_length=20)),
            ("occurred_at", models.DateTimeField()), ("reason", models.TextField(blank=True, default="")), ("metadata", models.JSONField(blank=True, default=dict)), ("event_key", models.CharField(max_length=200)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="application_events", to=settings.AUTH_USER_MODEL)),
            ("applicant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="application_events", to="applications.applicant")),
            ("application", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="history", to="applications.application")),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="application_events", to="workspaces.workspace")),
        ], options={"indexes": [models.Index(fields=["workspace", "application", "occurred_at"], name="applications_event_workspace_application_occurred_idx")]}),
        migrations.AddConstraint(model_name="application", constraint=models.CheckConstraint(condition=Q(requested_check_out_date__isnull=True) | Q(requested_check_in_date__isnull=True) | Q(requested_check_out_date__gte=F("requested_check_in_date")), name="application_dates_valid")),
        migrations.AddConstraint(model_name="application", constraint=models.UniqueConstraint(condition=Q(status__in=["draft", "submitted", "under_review"]), fields=["workspace", "applicant", "property"], name="application_active_applicant_property_uniq")),
        migrations.AddConstraint(model_name="applicationevent", constraint=models.UniqueConstraint(fields=["application", "event_key"], name="application_event_key_uniq")),
        migrations.RunSQL(sql="""
            ALTER TABLE applications_applicant ENABLE ROW LEVEL SECURITY;
            ALTER TABLE applications_applicant FORCE ROW LEVEL SECURITY;
            CREATE POLICY workspace_isolation_applications_applicant ON applications_applicant
                USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            ALTER TABLE applications_application ENABLE ROW LEVEL SECURITY;
            ALTER TABLE applications_application FORCE ROW LEVEL SECURITY;
            CREATE POLICY workspace_isolation_applications_application ON applications_application
                USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            ALTER TABLE applications_applicationevent ENABLE ROW LEVEL SECURITY;
            ALTER TABLE applications_applicationevent FORCE ROW LEVEL SECURITY;
            CREATE POLICY workspace_isolation_applications_applicationevent ON applications_applicationevent
                USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
        """, reverse_sql="""
            DROP POLICY IF EXISTS workspace_isolation_applications_applicationevent ON applications_applicationevent;
            ALTER TABLE applications_applicationevent NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE applications_applicationevent DISABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS workspace_isolation_applications_application ON applications_application;
            ALTER TABLE applications_application NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE applications_application DISABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS workspace_isolation_applications_applicant ON applications_applicant;
            ALTER TABLE applications_applicant NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE applications_applicant DISABLE ROW LEVEL SECURITY;
        """),
    ]
