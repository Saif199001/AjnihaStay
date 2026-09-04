from django.db import migrations


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"

POLICIES = {
    "properties_property": f"workspace_id = {WORKSPACE_ID}",
    "properties_propertyimage": f"property_id IN (SELECT id FROM properties_property WHERE workspace_id = {WORKSPACE_ID})",
    "unit_unit": f"property_id IN (SELECT id FROM properties_property WHERE workspace_id = {WORKSPACE_ID})",
    "unit_unitimage": f"unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "unit_subunit": f"unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "tenant_tenant": f"workspace_id = {WORKSPACE_ID}",
    "tenant_occupancy": f"tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})",
    "tenant_charge": f"occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID})",
    "payments_invoice": f"occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID})",
    "payments_payment": f"invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID})",
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

    with connection.cursor() as cursor:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0004_strengthen_workspace_rls"),
    ]

    operations = [
        migrations.RunPython(replace_policies, migrations.RunPython.noop),
    ]
