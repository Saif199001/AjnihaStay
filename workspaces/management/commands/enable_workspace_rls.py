from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


WORKSPACE_ID = "NULLIF(current_setting('app.workspace_id', true), '')::bigint"
WORKSPACE_FUNCTION = "workspace_rls_row_visible"
RLS_FUNCTION_OWNER = "ajnihastay_rls_owner"

TABLES = (
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
    "payments_paymentallocation",
    "payments_billingschedule",
    "payments_advancecredit",
    "payments_advancecreditapplication",
    "payments_financialadjustment",
    "payments_paymentrefund",
    "payments_financialledgerentry",
    "leasing_lease",
    "applications_applicant",
    "applications_application",
    "applications_applicationevent",
    "kyc_kycprofile",
    "kyc_kycdocument",
    "kyc_kycverificationevent",
    "kyc_kycdocumentevent",
    "kyc_agreementlink",
)

POLICIES = {table: f"{WORKSPACE_FUNCTION}('{table}', id)" for table in TABLES}


def find_unexpected_policies(cursor):
    """Return authoritative-table policies that are outside the locked policy contract."""
    expected = {f"workspace_isolation_{table}" for table in TABLES}
    cursor.execute(
        "SELECT tablename, policyname "
        "FROM pg_policies "
        "WHERE schemaname = 'public' "
        "AND tablename = ANY(%s) "
        "ORDER BY tablename, policyname",
        [[table.split(".")[-1] for table in TABLES]],
    )
    return sorted(
        (table, policy) for table, policy in cursor.fetchall() if policy not in expected
    )


FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {WORKSPACE_FUNCTION}(p_table text, p_id bigint)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_context_workspace_id bigint := NULLIF(current_setting('app.workspace_id', true), '')::bigint;
    v_row_workspace_id bigint;
BEGIN
    IF v_context_workspace_id IS NULL OR p_id IS NULL THEN
        RETURN FALSE;
    END IF;

    CASE p_table
        WHEN 'properties_property' THEN
            SELECT workspace_id INTO v_row_workspace_id FROM properties_property WHERE id = p_id;
        WHEN 'properties_propertyimage' THEN
            SELECT p.workspace_id INTO v_row_workspace_id FROM properties_propertyimage i JOIN properties_property p ON p.id = i.property_id WHERE i.id = p_id;
        WHEN 'unit_unit' THEN
            SELECT p.workspace_id INTO v_row_workspace_id FROM unit_unit u JOIN properties_property p ON p.id = u.property_id WHERE u.id = p_id;
        WHEN 'unit_unitimage' THEN
            SELECT p.workspace_id INTO v_row_workspace_id FROM unit_unitimage i JOIN unit_unit u ON u.id = i.unit_id JOIN properties_property p ON p.id = u.property_id WHERE i.id = p_id;
        WHEN 'unit_subunit' THEN
            SELECT p.workspace_id INTO v_row_workspace_id FROM unit_subunit s JOIN unit_unit u ON u.id = s.unit_id JOIN properties_property p ON p.id = u.property_id WHERE s.id = p_id;
        WHEN 'tenant_tenant' THEN
            SELECT workspace_id INTO v_row_workspace_id FROM tenant_tenant WHERE id = p_id;
        WHEN 'tenant_occupancy' THEN
            SELECT t.workspace_id INTO v_row_workspace_id FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id JOIN unit_unit u ON u.id = o.unit_id JOIN properties_property p ON p.id = u.property_id WHERE o.id = p_id AND p.workspace_id = t.workspace_id;
        WHEN 'tenant_charge' THEN
            SELECT t.workspace_id INTO v_row_workspace_id FROM tenant_charge c JOIN tenant_occupancy o ON o.id = c.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE c.id = p_id;
        WHEN 'payments_invoice' THEN
            SELECT t.workspace_id INTO v_row_workspace_id FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id JOIN unit_unit u ON u.id = o.unit_id JOIN properties_property p ON p.id = u.property_id WHERE i.id = p_id AND p.workspace_id = t.workspace_id;
        WHEN 'payments_payment' THEN
            SELECT workspace_id INTO v_row_workspace_id FROM payments_payment WHERE id = p_id;
        WHEN 'payments_paymentallocation' THEN
            SELECT p.workspace_id INTO v_row_workspace_id FROM payments_paymentallocation a JOIN payments_payment p ON p.id = a.payment_id JOIN payments_invoice i ON i.id = a.invoice_id JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE a.id = p_id AND p.workspace_id = t.workspace_id;
        WHEN 'payments_billingschedule' THEN
            SELECT t.workspace_id INTO v_row_workspace_id FROM payments_billingschedule b JOIN tenant_occupancy o ON o.id = b.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE b.id = p_id;
        WHEN 'payments_advancecredit' THEN
            SELECT ac.workspace_id INTO v_row_workspace_id FROM payments_advancecredit ac JOIN tenant_tenant t ON t.id = ac.tenant_id JOIN payments_payment p ON p.id = ac.source_payment_id WHERE ac.id = p_id AND t.workspace_id = ac.workspace_id AND p.workspace_id = ac.workspace_id AND (ac.occupancy_id IS NULL OR EXISTS (SELECT 1 FROM tenant_occupancy o WHERE o.id = ac.occupancy_id AND o.tenant_id = ac.tenant_id));
        WHEN 'payments_advancecreditapplication' THEN
            SELECT ac.workspace_id INTO v_row_workspace_id FROM payments_advancecreditapplication a JOIN payments_advancecredit ac ON ac.id = a.credit_id JOIN payments_invoice i ON i.id = a.invoice_id JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE a.id = p_id AND ac.workspace_id = t.workspace_id;
        WHEN 'payments_financialadjustment' THEN
            SELECT fa.workspace_id INTO v_row_workspace_id FROM payments_financialadjustment fa JOIN payments_invoice i ON i.id = fa.invoice_id JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE fa.id = p_id AND fa.workspace_id = t.workspace_id;
        WHEN 'payments_paymentrefund' THEN
            SELECT r.workspace_id INTO v_row_workspace_id FROM payments_paymentrefund r JOIN payments_payment p ON p.id = r.payment_id WHERE r.id = p_id AND r.workspace_id = p.workspace_id;
        WHEN 'payments_financialledgerentry' THEN
            SELECT le.workspace_id INTO v_row_workspace_id FROM payments_financialledgerentry le WHERE le.id = p_id AND (le.invoice_id IS NULL OR EXISTS (SELECT 1 FROM payments_invoice i JOIN tenant_occupancy o ON o.id = i.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE i.id = le.invoice_id AND t.workspace_id = le.workspace_id)) AND (le.payment_id IS NULL OR EXISTS (SELECT 1 FROM payments_payment p WHERE p.id = le.payment_id AND p.workspace_id = le.workspace_id)) AND (le.occupancy_id IS NULL OR EXISTS (SELECT 1 FROM tenant_occupancy o JOIN tenant_tenant t ON t.id = o.tenant_id WHERE o.id = le.occupancy_id AND t.workspace_id = le.workspace_id));
        WHEN 'leasing_lease' THEN
            SELECT l.workspace_id INTO v_row_workspace_id FROM leasing_lease l JOIN tenant_occupancy o ON o.id = l.occupancy_id JOIN tenant_tenant t ON t.id = o.tenant_id WHERE l.id = p_id AND l.workspace_id = t.workspace_id;
        WHEN 'applications_applicant' THEN
            SELECT workspace_id INTO v_row_workspace_id FROM applications_applicant WHERE id = p_id;
        WHEN 'applications_application' THEN
            SELECT a.workspace_id INTO v_row_workspace_id FROM applications_application a JOIN applications_applicant ap ON ap.id = a.applicant_id JOIN properties_property p ON p.id = a.property_id WHERE a.id = p_id AND a.workspace_id = ap.workspace_id AND a.workspace_id = p.workspace_id;
        WHEN 'applications_applicationevent' THEN
            SELECT e.workspace_id INTO v_row_workspace_id FROM applications_applicationevent e JOIN applications_application a ON a.id = e.application_id JOIN applications_applicant ap ON ap.id = e.applicant_id WHERE e.id = p_id AND e.workspace_id = a.workspace_id AND e.workspace_id = ap.workspace_id;
        WHEN 'kyc_kycprofile' THEN
            SELECT k.workspace_id INTO v_row_workspace_id FROM kyc_kycprofile k JOIN tenant_tenant t ON t.id = k.tenant_id WHERE k.id = p_id AND k.workspace_id = t.workspace_id;
        WHEN 'kyc_kycdocument' THEN
            SELECT d.workspace_id INTO v_row_workspace_id FROM kyc_kycdocument d JOIN tenant_tenant t ON t.id = d.tenant_id WHERE d.id = p_id AND d.workspace_id = t.workspace_id;
        WHEN 'kyc_kycverificationevent' THEN
            SELECT e.workspace_id INTO v_row_workspace_id FROM kyc_kycverificationevent e JOIN kyc_kycprofile k ON k.id = e.kyc_profile_id JOIN tenant_tenant t ON t.id = e.tenant_id WHERE e.id = p_id AND e.workspace_id = k.workspace_id AND e.workspace_id = t.workspace_id;
        WHEN 'kyc_kycdocumentevent' THEN
            SELECT e.workspace_id INTO v_row_workspace_id FROM kyc_kycdocumentevent e JOIN kyc_kycdocument d ON d.id = e.document_id JOIN tenant_tenant t ON t.id = e.tenant_id WHERE e.id = p_id AND e.workspace_id = d.workspace_id AND e.workspace_id = t.workspace_id;
        WHEN 'kyc_agreementlink' THEN
            SELECT a.workspace_id INTO v_row_workspace_id FROM kyc_agreementlink a JOIN tenant_tenant t ON t.id = a.tenant_id JOIN tenant_occupancy o ON o.id = a.occupancy_id WHERE a.id = p_id AND a.workspace_id = t.workspace_id AND o.tenant_id = a.tenant_id AND (a.lease_id IS NULL OR EXISTS (SELECT 1 FROM leasing_lease l WHERE l.id = a.lease_id AND l.workspace_id = a.workspace_id));
        ELSE
            RETURN FALSE;
    END CASE;

    RETURN v_row_workspace_id IS NOT NULL AND v_row_workspace_id = v_context_workspace_id;
END;
$fn$;
"""


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
                    raise CommandError("Workspace RLS inventory contains missing tables: " + ", ".join(missing))

                unexpected = find_unexpected_policies(cursor)
                if unexpected:
                    details = ", ".join(f"{table}.{policy}" for table, policy in unexpected)
                    raise CommandError(
                        "Workspace RLS policy inventory contains unexpected policies: " + details
                    )

                cursor.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname = %s",
                    [RLS_FUNCTION_OWNER],
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        f"CREATE ROLE {RLS_FUNCTION_OWNER} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS"
                    )
                else:
                    cursor.execute(
                        f"ALTER ROLE {RLS_FUNCTION_OWNER} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS"
                    )

                cursor.execute(FUNCTION_SQL)
                cursor.execute(
                    f"ALTER FUNCTION {WORKSPACE_FUNCTION}(text, bigint) OWNER TO {RLS_FUNCTION_OWNER}"
                )
                for table in TABLES:
                    cursor.execute(f"GRANT SELECT ON TABLE {table} TO {RLS_FUNCTION_OWNER}")

                # The resolver is executable only by the database role running the
                # RLS installation command. This replaces the unsafe PUBLIC grant.
                cursor.execute(
                    f"REVOKE ALL ON FUNCTION {WORKSPACE_FUNCTION}(text, bigint) FROM PUBLIC"
                )
                cursor.execute(
                    f"GRANT EXECUTE ON FUNCTION {WORKSPACE_FUNCTION}(text, bigint) TO CURRENT_USER"
                )

                for table in TABLES:
                    policy_name = f"workspace_isolation_{table}"
                    expression = POLICIES[table]
                    cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                    cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                    cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
                    cursor.execute(f"CREATE POLICY {policy_name} ON {table} USING ({expression}) WITH CHECK ({expression})")

        self.stdout.write(self.style.SUCCESS(f"Workspace row-level security enabled, forced, and policy-synchronized for {len(TABLES)} tables."))
