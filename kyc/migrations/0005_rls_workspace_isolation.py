from django.db import migrations


PROTECTED_TABLES = (
    "kyc_kycprofile",
    "kyc_kycdocument",
    "kyc_kycverificationevent",
    "kyc_kycdocumentevent",
    "kyc_agreementlink",
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
    dependencies = [("kyc", "0004_align_document_event_index_name")]
    operations = [migrations.RunPython(install_policies, remove_policies)]
