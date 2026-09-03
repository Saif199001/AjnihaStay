from django.db import migrations


POLICIES = {
    "tenant_occupancy": "tenant_id IN (SELECT t.id FROM tenant_tenant t WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint) AND unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "payments_invoice": "occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id JOIN unit_unit u ON u.id = o.unit_id JOIN properties_property p ON p.id = u.property_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint AND p.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "payments_payment": "invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id JOIN unit_unit u ON u.id = o.unit_id JOIN properties_property p ON p.id = u.property_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint AND p.workspace_id = current_setting('app.workspace_id', true)::bigint)",
}


def replace_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table, expression in POLICIES.items():
            policy_name = f"workspace_isolation_{table}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
            cursor.execute(
                f"CREATE POLICY {policy_name} ON {table} USING ({expression}) WITH CHECK ({expression})"
            )


def restore_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    expressions = {
        "tenant_occupancy": "tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = current_setting('app.workspace_id', true)::bigint)",
        "payments_invoice": "occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint)",
        "payments_payment": "invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    }

    with schema_editor.connection.cursor() as cursor:
        for table, expression in expressions.items():
            policy_name = f"workspace_isolation_{table}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
            cursor.execute(
                f"CREATE POLICY {policy_name} ON {table} USING ({expression}) WITH CHECK ({expression})"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0003_row_level_security_policies"),
    ]

    operations = [
        migrations.RunPython(replace_policies, restore_policies),
    ]
