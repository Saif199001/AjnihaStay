from django.db import migrations


PROTECTED_TABLES = (
    "properties_property",
    "properties_propertyimage",
    "unit_unit",
    "unit_unitimage",
    "unit_subunit",
    "tenant_tenant",
    "tenant_occupancy",
    "tenant_charge",
    "payments_invoice",
    "payments_payment",
)


POLICIES = {
    "properties_property": "workspace_id = current_setting('app.workspace_id', true)::bigint",
    "properties_propertyimage": "property_id IN (SELECT id FROM properties_property WHERE workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "unit_unit": "property_id IN (SELECT id FROM properties_property WHERE workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "unit_unitimage": "unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "unit_subunit": "unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "tenant_tenant": "workspace_id = current_setting('app.workspace_id', true)::bigint",
    "tenant_occupancy": "tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "tenant_charge": "occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "payments_invoice": "occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint)",
    "payments_payment": "invoice_id IN (SELECT i.id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = current_setting('app.workspace_id', true)::bigint)",
}


def create_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            expression = POLICIES[table]
            cursor.execute(f"CREATE POLICY workspace_isolation_{table} ON {table} USING ({expression}) WITH CHECK ({expression})")


def drop_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table in reversed(PROTECTED_TABLES):
            cursor.execute(f"DROP POLICY IF EXISTS workspace_isolation_{table} ON {table}")


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0002_bootstrap_workspaces"),
        ("properties", "0003_property_has_subunits_alter_property_property_type"),
        ("tenant", "0002_workspace"),
        ("unit", "0001_initial"),
        ("payments", "0003_alter_invoice_total_amount_and_more"),
    ]

    operations = [
        migrations.RunPython(create_policies, drop_policies),
    ]
