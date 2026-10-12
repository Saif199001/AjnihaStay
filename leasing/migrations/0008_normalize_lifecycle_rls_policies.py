from django.db import migrations


# Earlier migrations used inconsistent policy names and app.current_workspace_id.
# Each lifecycle row must also point to a lease in the same workspace; matching
# only the row's workspace_id is not sufficient to enforce relational isolation.
TABLE_POLICIES = (
    ("leasing_leaselifecycleevent", "workspace_isolation_leasing_leaselifecycleevent", "workspace_isolation_leaselifecycleevent", "lease_id"),
    ("leasing_leasenotice", "workspace_isolation_leasing_leasenotice", "workspace_isolation_leasenotice", "lease_id"),
    ("leasing_leaserenewal", "workspace_isolation_leasing_leaserenewal", "workspace_isolation_leasingleaserenewal", "source_lease_id"),
    ("leasing_leasecontractversion", "workspace_isolation_leasing_leasecontractversion", "workspace_isolation_leasingleasecontractversion", "lease_id"),
)


def normalize_policy_names(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table, canonical_name, legacy_name, lease_fk in TABLE_POLICIES:
            cursor.execute(f"DROP POLICY IF EXISTS {legacy_name} ON {table}")
            cursor.execute(f"DROP POLICY IF EXISTS {canonical_name} ON {table}")
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            relationship_check = (
                "EXISTS ("
                "SELECT 1 FROM leasing_lease AS parent_lease "
                f"WHERE parent_lease.id = {table}.{lease_fk} "
                f"AND parent_lease.workspace_id = {table}.workspace_id"
                ")"
            )
            cursor.execute(
                f"""
                CREATE POLICY {canonical_name} ON {table}
                USING (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    AND {relationship_check}
                )
                WITH CHECK (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                    AND {relationship_check}
                )
                """
            )


def restore_legacy_policy_names(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table, canonical_name, legacy_name, lease_fk in reversed(TABLE_POLICIES):
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
