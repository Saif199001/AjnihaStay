from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("kyc", "0002_align_model_index_names"),
    ]

    operations = [
        migrations.CreateModel(
            name="KycDocumentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("occurred_at", models.DateTimeField()),
                ("reason", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("event_key", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_document_events", to=settings.AUTH_USER_MODEL)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lifecycle_events", to="kyc.kycdocument")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_document_events", to="tenant.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kyc_document_events", to="workspaces.workspace")),
            ],
            options={"indexes": [models.Index(fields=["workspace", "tenant", "occurred_at"], name="kyc_kycdocume_workspa_2b4a6d_idx")]},
        ),
        migrations.AddConstraint(
            model_name="kycdocumentevent",
            constraint=models.UniqueConstraint(fields=["document", "event_key"], name="kyc_doc_event_key_uniq"),
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE kyc_kycdocumentevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocumentevent FORCE ROW LEVEL SECURITY;
                CREATE POLICY workspace_isolation_kyc_kycdocumentevent ON kyc_kycdocumentevent
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocumentevent ON kyc_kycdocumentevent;
                ALTER TABLE kyc_kycdocumentevent NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocumentevent DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
