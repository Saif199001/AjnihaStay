from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"

# Authoritative inventory of every currently workspace-owned domain table.
# Every entry has an explicit USING/WITH CHECK workspace-isolation contract.
POLICIES = {
    "properties_property": f"workspace_id = {WORKSPACE_ID}",
    "properties_propertyimage": f"property_id IN (SELECT id FROM properties_property WHERE workspace_id = {WORKSPACE_ID})",
    "unit_unit": f"property_id IN (SELECT id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "unit_unitimage": f"unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "unit_subunit": f"unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "tenant_tenant": f"workspace_id = {WORKSPACE_ID}",
    "tenant_occupancy": f"tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}) AND unit_id IN (SELECT u.id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE p.workspace_id = {WORKSPACE_ID})",
    "tenant_charge": f"occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID})",
    "payments_invoice": f"occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id JOIN unit_unit u ON u.id = o.unit_id JOIN properties_property p ON p.id = u.property_id WHERE t.workspace_id = {WORKSPACE_ID} AND p.workspace_id = {WORKSPACE_ID})",
    # Payment has an explicit workspace FK. This is deliberately not derived
    # from invoice because pure advance payments are invoice-less.
    "payments_payment": f"workspace_id = {WORKSPACE_ID}",
    "payments_paymentallocation": f"payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = {WORKSPACE_ID}) AND invoice_id IN (SELECT id FROM payments_invoice WHERE occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID}))",
    # BillingSchedule has no direct workspace FK; workspace is derived from occupancy.
    "payments_billingschedule": f"occupancy_id IN (SELECT id FROM tenant_occupancy WHERE tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}))",
    "payments_advancecredit": f"workspace_id = {WORKSPACE_ID} AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}) AND (occupancy_id IS NULL OR occupancy_id IN (SELECT id FROM tenant_occupancy WHERE tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}))) AND source_payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = {WORKSPACE_ID})",
    "payments_advancecreditapplication": f"credit_id IN (SELECT id FROM payments_advancecredit WHERE workspace_id = {WORKSPACE_ID}) AND invoice_id IN (SELECT id FROM payments_invoice WHERE occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID}))",
    "payments_financialadjustment": f"workspace_id = {WORKSPACE_ID} AND invoice_id IN (SELECT id FROM payments_invoice WHERE occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID}))",
    "payments_paymentrefund": f"workspace_id = {WORKSPACE_ID} AND payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = {WORKSPACE_ID})",
    "payments_financialledgerentry": f"workspace_id = {WORKSPACE_ID} AND (invoice_id IS NULL OR invoice_id IN (SELECT id FROM payments_invoice WHERE occupancy_id IN (SELECT o.id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE t.workspace_id = {WORKSPACE_ID}))) AND (payment_id IS NULL OR payment_id IN (SELECT id FROM payments_payment WHERE workspace_id = {WORKSPACE_ID})) AND (occupancy_id IS NULL OR occupancy_id IN (SELECT id FROM tenant_occupancy WHERE tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})))",
    "leasing_lease": f"workspace_id = {WORKSPACE_ID} AND occupancy_id IN (SELECT id FROM tenant_occupancy WHERE tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}))",
    "applications_applicant": f"workspace_id = {WORKSPACE_ID}",
    "applications_application": f"workspace_id = {WORKSPACE_ID} AND applicant_id IN (SELECT id FROM applications_applicant WHERE workspace_id = {WORKSPACE_ID}) AND property_id IN (SELECT id FROM properties_property WHERE workspace_id = {WORKSPACE_ID})",
    "applications_applicationevent": f"workspace_id = {WORKSPACE_ID} AND application_id IN (SELECT id FROM applications_application WHERE workspace_id = {WORKSPACE_ID}) AND applicant_id IN (SELECT id FROM applications_applicant WHERE workspace_id = {WORKSPACE_ID})",
    "kyc_kycprofile": f"workspace_id = {WORKSPACE_ID} AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})",
    "kyc_kycdocument": f"workspace_id = {WORKSPACE_ID} AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})",
    "kyc_kycverificationevent": f"workspace_id = {WORKSPACE_ID} AND kyc_profile_id IN (SELECT id FROM kyc_kycprofile WHERE workspace_id = {WORKSPACE_ID}) AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})",
    "kyc_kycdocumentevent": f"workspace_id = {WORKSPACE_ID} AND document_id IN (SELECT id FROM kyc_kycdocument WHERE workspace_id = {WORKSPACE_ID}) AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})",
    "kyc_agreementlink": f"workspace_id = {WORKSPACE_ID} AND tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID}) AND occupancy_id IN (SELECT id FROM tenant_occupancy WHERE tenant_id IN (SELECT id FROM tenant_tenant WHERE workspace_id = {WORKSPACE_ID})) AND (lease_id IS NULL OR lease_id IN (SELECT id FROM leasing_lease WHERE workspace_id = {WORKSPACE_ID}))",
}

TABLES = tuple(POLICIES)


class Command(BaseCommand):
    help = "Enable, force, and install authoritative PostgreSQL workspace RLS policies."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Workspace RLS requires PostgreSQL.")

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                missing = sorted(set(TABLES) - existing_tables)
                if missing:
                    raise CommandError(
                        "Workspace RLS inventory contains missing tables: " + ", ".join(missing)
                    )

                for table in TABLES:
                    policy_name = f"workspace_isolation_{table}"
                    expression = POLICIES[table]
                    cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                    cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                    cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
                    cursor.execute(
                        f"CREATE POLICY {policy_name} ON {table} USING ({expression}) WITH CHECK ({expression})"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Workspace row-level security enabled, forced, and policy-synchronized for {len(TABLES)} tables."
            )
        )
