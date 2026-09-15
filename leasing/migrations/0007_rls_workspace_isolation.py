from django.db import migrations


PROTECTED_TABLES = (
    "leasing_lease",
    "leasing_leasecontractversion",
    "leasing_leaselifecycleevent",
)


def enable_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
            cursor.execute(
                f"""
                CREATE POLICY {table}_workspace_isolation ON {table}
                USING (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                )
                WITH CHECK (
                    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint
                )
                """
            )


def disable_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            cursor.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("leasing", "0006_lease_contract_version")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
