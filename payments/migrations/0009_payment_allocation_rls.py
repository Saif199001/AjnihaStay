from django.db import migrations


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"

NEW_PAYMENT_POLICY = f"workspace_id = {WORKSPACE_ID}"
ALLOCATION_POLICY = (
    f"payment_id IN (SELECT p.id FROM payments_payment p WHERE p.workspace_id = {WORKSPACE_ID}) "
    f"AND invoice_id IN (SELECT i.id FROM payments_invoice i "
    f"JOIN tenant_occupancy o ON o.id = i.occupancy_id "
    f"JOIN tenant_tenant t ON t.id = o.tenant_id "
    f"WHERE t.workspace_id = {WORKSPACE_ID})"
)
LEGACY_PAYMENT_POLICY = (
    f"invoice_id IN (SELECT i.id FROM payments_invoice i "
    f"JOIN tenant_occupancy o ON o.id = i.occupancy_id "
    f"JOIN tenant_tenant t ON t.id = o.tenant_id "
    f"WHERE t.workspace_id = {WORKSPACE_ID})"
)


def apply_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_payment ON payments_payment")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_payment ON payments_payment "
            f"USING ({NEW_PAYMENT_POLICY}) WITH CHECK ({NEW_PAYMENT_POLICY})"
        )
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_paymentallocation ON payments_paymentallocation"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_paymentallocation ON payments_paymentallocation "
            f"USING ({ALLOCATION_POLICY}) WITH CHECK ({ALLOCATION_POLICY})"
        )


def reverse_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS workspace_isolation_payments_paymentallocation ON payments_paymentallocation"
        )
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_payment ON payments_payment")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_payment ON payments_payment "
            f"USING ({LEGACY_PAYMENT_POLICY}) WITH CHECK ({LEGACY_PAYMENT_POLICY})"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0008_merge_payment_allocation_heads"),
        ("workspaces", "0006_rls_fail_closed"),
    ]

    operations = [
        migrations.RunPython(apply_rls_policies, reverse_rls_policies),
    ]
