from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0006_lease_lifecycle_event_key"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE leasing_lease ENABLE ROW LEVEL SECURITY;
                ALTER TABLE leasing_lease FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_leasinglease ON leasing_lease;
                CREATE POLICY workspace_isolation_leasinglease
                    ON leasing_lease
                    USING (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    )
                    WITH CHECK (
                        workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    );
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_leasinglease ON leasing_lease;
                ALTER TABLE leasing_lease NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE leasing_lease DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
