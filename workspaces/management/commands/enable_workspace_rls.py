from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


# Authoritative inventory of tables that carry a direct workspace_id FK.
# Policy creation is migration-owned; this command is the deployment-time
# safety net that guarantees RLS remains ENABLED + FORCED on every table.
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


class Command(BaseCommand):
    help = "Enable and FORCE PostgreSQL row-level security for workspace-owned domain tables."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Workspace RLS requires PostgreSQL.")

        with transaction.atomic():
            with connection.cursor() as cursor:
                for table in TABLES:
                    cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                    cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        self.stdout.write(
            self.style.SUCCESS(
                f"Workspace row-level security enabled and forced for {len(TABLES)} tables."
            )
        )
