from django.db import migrations


PROTECTED_TABLES = (
    "applications_applicant",
    "applications_application",
    "applications_applicationevent",
)


def enable_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            cursor.execute(
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
            cursor.execute(
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
            cursor.execute(
                f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}"
            )
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
    dependencies = [("applications", "0002_shorten_index_names")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
