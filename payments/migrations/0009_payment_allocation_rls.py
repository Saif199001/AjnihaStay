from django.db import migrations


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"

PAYMENT_POLICY = "workspace_id = {workspace_id}".format(workspace_id=WORKSPACE_ID)
ALLOCATION_POLICY = (
    "payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = {workspace_id})"
    .format(workspace_id=WORKSPACE_ID)
)


def apply_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_payment ON payments_payment")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_payment ON payments_payment "
            f"USING ({PAYMENT_POLICY}) WITH CHECK ({PAYMENT_POLICY})"
        )
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_paymentallocation ON payments_paymentallocation "
            f"USING ({ALLOCATION_POLICY}) WITH CHECK ({ALLOCATION_POLICY})"
        )


def reverse_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_paymentallocation ON payments_paymentallocation")
        cursor.execute("DROP POLICY IF EXISTS workspace_isolation_payments_payment ON payments_payment")
        cursor.execute(
            "CREATE POLICY workspace_isolation_payments_payment ON payments_payment "
            f"USING ({ALLOCATION_POLICY.replace('payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = ', 'invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = ')}) WITH CHECK ({ALLOCATION_POLICY.replace('payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = ', 'invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.occupancy_id WHERE t.workspace_id = ')})"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0008_merge_payment_allocation_heads"),
    ]

    operations = [
        migrations.RunPython(apply_rls_policies, reverse_rls_policies),
    ]
