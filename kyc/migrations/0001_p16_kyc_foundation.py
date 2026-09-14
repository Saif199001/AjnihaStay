from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenant", "0009_alter_tenant_profile_photo"),
        ("leasing", "0006_lease_lifecycle_event_key"),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="KycProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("unverified", "Unverified"), ("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")], default="unverified", max_length=20)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rejected_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="kyc_profiles_rejected", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_profile", to="tenant.tenant")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="kyc_profiles_verified", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_profiles", to="workspaces.workspace")),
            ],
            options={"indexes": [models.Index(fields=["workspace", "status"], name="kyc_profile_ws_status_idx")]},
        ),
        migrations.CreateModel(
            name="KycDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(max_length=50)),
                ("document_number", models.CharField(blank=True, default="", max_length=100)),
                ("storage_key", models.CharField(max_length=500)),
                ("content_type", models.CharField(max_length=100)),
                ("file_size", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("uploaded", "Uploaded"), ("under_review", "Under review"), ("verified", "Verified"), ("rejected", "Rejected"), ("expired", "Expired")], default="uploaded", max_length=20)),
                ("issued_at", models.DateField(blank=True, null=True)),
                ("expires_at", models.DateField(blank=True, null=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rejected_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="kyc_documents_rejected", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_documents", to="tenant.tenant")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_documents_uploaded", to=settings.AUTH_USER_MODEL)),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="kyc_documents_verified", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_documents", to="workspaces.workspace")),
            ],
            options={"indexes": [models.Index(fields=["workspace", "tenant", "status"], name="kyc_doc_ws_tenant_status_idx"), models.Index(fields=["workspace", "expires_at"], name="kyc_doc_ws_expiry_idx")]},
        ),
        migrations.CreateModel(
            name="KycVerificationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("occurred_at", models.DateTimeField()),
                ("reason", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("event_key", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_verification_events", to=settings.AUTH_USER_MODEL)),
                ("kyc_profile", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="verification_events", to="kyc.kycprofile")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_verification_events", to="tenant.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_verification_events", to="workspaces.workspace")),
            ],
            options={"indexes": [models.Index(fields=["workspace", "tenant", "occurred_at"], name="kyc_event_ws_tenant_time_idx")]},
        ),
        migrations.CreateModel(
            name="AgreementLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agreement_type", models.CharField(max_length=50)),
                ("reference", models.CharField(blank=True, default="", max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agreement_links_created", to=settings.AUTH_USER_MODEL)),
                ("lease", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="agreement_links", to="leasing.lease")),
                ("occupancy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agreement_links", to="tenant.occupancy")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agreement_links", to="tenant.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agreement_links", to="workspaces.workspace")),
            ],
            options={"indexes": [models.Index(fields=["workspace", "tenant"], name="agreement_ws_tenant_idx"), models.Index(fields=["workspace", "occupancy"], name="agreement_ws_occ_idx"), models.Index(fields=["workspace", "lease"], name="agreement_ws_lease_idx")]},
        ),
        migrations.AddConstraint(
            model_name="kycprofile",
            constraint=models.CheckConstraint(condition=Q(status__in=["unverified", "pending", "verified", "rejected"]), name="kyc_profile_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="kycdocument",
            constraint=models.CheckConstraint(condition=Q(status__in=["uploaded", "under_review", "verified", "rejected", "expired"]), name="kyc_document_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="kycdocument",
            constraint=models.CheckConstraint(condition=Q(file_size__gt=0), name="kyc_document_size_positive"),
        ),
        migrations.AddConstraint(
            model_name="kycdocument",
            constraint=models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(issued_at__isnull=True) | Q(expires_at__gte=F("issued_at")), name="kyc_document_expiry_valid"),
        ),
        migrations.AddConstraint(
            model_name="kycverificationevent",
            constraint=models.UniqueConstraint(fields=["kyc_profile", "event_key"], name="kyc_event_profile_key_uniq"),
        ),
        migrations.AddConstraint(
            model_name="agreementlink",
            constraint=models.UniqueConstraint(fields=["workspace", "tenant", "occupancy", "agreement_type", "reference"], name="agreement_link_logical_uniq"),
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE kyc_kycprofile ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycprofile FORCE ROW LEVEL SECURITY;
                CREATE POLICY workspace_isolation_kyc_kycprofile ON kyc_kycprofile
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
                ALTER TABLE kyc_kycdocument ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocument FORCE ROW LEVEL SECURITY;
                CREATE POLICY workspace_isolation_kyc_kycdocument ON kyc_kycdocument
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
                ALTER TABLE kyc_kycverificationevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycverificationevent FORCE ROW LEVEL SECURITY;
                CREATE POLICY workspace_isolation_kyc_kycverificationevent ON kyc_kycverificationevent
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
                ALTER TABLE kyc_agreementlink ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_agreementlink FORCE ROW LEVEL SECURITY;
                CREATE POLICY workspace_isolation_kyc_agreementlink ON kyc_agreementlink
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycprofile ON kyc_kycprofile;
                ALTER TABLE kyc_kycprofile NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycprofile DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocument ON kyc_kycdocument;
                ALTER TABLE kyc_kycdocument NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocument DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycverificationevent ON kyc_kycverificationevent;
                ALTER TABLE kyc_kycverificationevent NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycverificationevent DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_agreementlink ON kyc_agreementlink;
                ALTER TABLE kyc_agreementlink NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_agreementlink DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
