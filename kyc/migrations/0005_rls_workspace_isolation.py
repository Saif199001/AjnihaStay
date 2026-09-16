from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("kyc", "0004_align_document_event_index_name"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE kyc_kycprofile ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycprofile FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycprofile ON kyc_kycprofile;
                CREATE POLICY workspace_isolation_kyc_kycprofile
                    ON kyc_kycprofile
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );

                ALTER TABLE kyc_kycdocument ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocument FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocument ON kyc_kycdocument;
                CREATE POLICY workspace_isolation_kyc_kycdocument
                    ON kyc_kycdocument
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );

                ALTER TABLE kyc_kycverificationevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycverificationevent FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycverificationevent ON kyc_kycverificationevent;
                CREATE POLICY workspace_isolation_kyc_kycverificationevent
                    ON kyc_kycverificationevent
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );

                ALTER TABLE kyc_agreementlink ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kyc_agreementlink FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_agreementlink ON kyc_agreementlink;
                CREATE POLICY workspace_isolation_kyc_agreementlink
                    ON kyc_agreementlink
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_kyc_agreementlink ON kyc_agreementlink;
                ALTER TABLE kyc_agreementlink NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_agreementlink DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycverificationevent ON kyc_kycverificationevent;
                ALTER TABLE kyc_kycverificationevent NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycverificationevent DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycdocument ON kyc_kycdocument;
                ALTER TABLE kyc_kycdocument NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycdocument DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_kyc_kycprofile ON kyc_kycprofile;
                ALTER TABLE kyc_kycprofile NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE kyc_kycprofile DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
