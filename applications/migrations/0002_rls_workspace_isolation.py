from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE applications_applicant ENABLE ROW LEVEL SECURITY;
                ALTER TABLE applications_applicant FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_applications_applicant ON applications_applicant;
                CREATE POLICY workspace_isolation_applications_applicant
                    ON applications_applicant
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );

                ALTER TABLE applications_application ENABLE ROW LEVEL SECURITY;
                ALTER TABLE applications_application FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_applications_application ON applications_application;
                CREATE POLICY workspace_isolation_applications_application
                    ON applications_application
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );

                ALTER TABLE applications_applicationevent ENABLE ROW LEVEL SECURITY;
                ALTER TABLE applications_applicationevent FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_applications_applicationevent ON applications_applicationevent;
                CREATE POLICY workspace_isolation_applications_applicationevent
                    ON applications_applicationevent
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_applications_applicationevent ON applications_applicationevent;
                ALTER TABLE applications_applicationevent NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE applications_applicationevent DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_applications_application ON applications_application;
                ALTER TABLE applications_application NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE applications_application DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_applications_applicant ON applications_applicant;
                ALTER TABLE applications_applicant NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE applications_applicant DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
