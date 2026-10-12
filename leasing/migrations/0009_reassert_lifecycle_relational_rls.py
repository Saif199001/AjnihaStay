from django.db import migrations


# Forward-only repair for databases that already recorded leasing.0008 before
# its relational policy definition was corrected in source control.
TABLE_POLICIES = (
    ("leasing_leaselifecycleevent", "workspace_isolation_leasing_leaselifecycleevent", "workspace_isolation_leaselifecycleevent", "lease_id"),
    ("leasing_leasenotice", "workspace_isolation_leasing_leasenotice", "workspace_isolation_leasenotice", "lease_id"),
    ("leasing_leaserenewal", "workspace_isolation_leasing_leaserenewal", "workspace_isolation_leasingleaserenewal", "source_lease_id"),
    ("leasing_leasecontractversion", "workspace_isolation_leasing_leasecontractversion", "workspace_isolation_leasingleasecontractversion", "lease_id"),
)


def apply_relational_policies(apps, schema_editor):
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


def reverse_relational_policies(apps, schema_editor):
    # Reverse to the corrected 0008 policy contract, not the historical
    # workspace_id-only policies that existed in some deployed databases.
    apply_relational_policies(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0008_normalize_lifecycle_rls_policies"),
    ]

    operations = [
        migrations.RunPython(apply_relational_policies, reverse_relational_policies),
    ]
