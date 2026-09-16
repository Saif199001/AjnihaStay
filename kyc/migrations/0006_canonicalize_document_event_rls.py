from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("kyc", "0005_rls_workspace_isolation"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE kyc_kycdocumentevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocumentevent FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocumentevent ON kyc_kycdocumentevent;
                CREATE POLICY workspace_isolation_kyc_kycdocumentevent
                    ON kyc_kycdocumentevent
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocumentevent ON kyc_kycdocumentevent;
                CREATE POLICY workspace_isolation_kyc_kycdocumentevent
                    ON kyc_kycdocumentevent
                    USING (
                        workspace_id = current_setting('app.current_workspace_id', true)::bigint
                    )
                    WITH CHECK (
                        workspace_id = current_setting('app.current_workspace_id', true)::bigint
                    );
                ALTER TABLE kyc_kycdocumentevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocumentevent FORCE ROW LEVEL SECURITY;
            """,
        ),
    ]
