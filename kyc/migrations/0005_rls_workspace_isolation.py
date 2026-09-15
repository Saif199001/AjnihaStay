from django.db import migrations


PROTECTED_TABLES = (
    "kyc_kycprofile",
    "kyc_kycdocument",
    "kyc_kycverificationevent",
    "kyc_kycdocumentevent",
    "kyc_agreementlink",
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
    dependencies = [("kyc", "0004_align_document_event_index_name")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
