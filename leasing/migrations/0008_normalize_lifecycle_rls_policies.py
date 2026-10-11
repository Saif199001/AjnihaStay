from django.db import migrations


# Earlier migrations used inconsistent policy names and app.current_workspace_id.
# Normalize to the central app.workspace_id policy contract.
TABLE_POLICIES = (
    ("leasing_leaselifecycleevent", "workspace_isolation_leasing_leaselifecycleevent", "workspace_isolation_leaselifecycleevent"),
    ("leasing_leasenotice", "workspace_isolation_leasing_leasenotice", "workspace_isolation_leasenotice"),
    ("leasing_leaserenewal", "workspace_isolation_leasing_leaserenewal", "workspace_isolation_leasingleaserenewal"),
    ("leasing_leasecontractversion", "workspace_isolation_leasing_leasecontractversion", "workspace_isolation_leasingleasecontractversion"),
)


def normalize_policy_names(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table, canonical_name, legacy_name in TABLE_POLICIES:
            cursor.execute(f"DROP POLICY IF EXISTS {legacy_name} ON {table}")
            cursor.execute(f"DROP POLICY IF EXISTS {canonical_name} ON {table}")
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"""
                CREATE POLICY {canonical_name} ON {table}
                USING (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                )
                WITH CHECK (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                )
                """
            )


def restore_legacy_policy_names(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table, canonical_name, legacy_name in reversed(TABLE_POLICIES):
            cursor.execute(f"DROP POLICY IF EXISTS {canonical_name} ON {table}")
            cursor.execute(
                f"""
                CREATE POLICY {legacy_name} ON {table}
                USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::bigint)
                WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::bigint)
                """
            )


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0007_rls_workspace_isolation"),
    ]

    operations = [
        migrations.RunPython(normalize_policy_names, restore_legacy_policy_names),
    ]
