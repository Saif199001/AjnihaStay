from django.db import migrations


PROTECTED_TABLES = (
    "leasing_lease",
    "leasing_leaselifecycleevent",
    "leasing_leasenotice",
    "leasing_leaserenewal",
    "leasing_leasecontractversion",
)


def install_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            policy_name = f"workspace_isolation_{table}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                USING (workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint)
                WITH CHECK (workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint)
                """
            )


def remove_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            cursor.execute(f"DROP POLICY IF EXISTS workspace_isolation_{table} ON {table}")


class Migration(migrations.Migration):
    dependencies = [("leasing", "0006_lease_contract_version")]
    operations = [migrations.RunPython(install_policies, remove_policies)]
