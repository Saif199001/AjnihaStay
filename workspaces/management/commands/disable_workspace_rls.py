from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


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
    "payments_finalsettlement",
    "payments_financialledgerentry",
    "applications_applicant",
    "applications_application",
    "applications_applicationevent",
    "kyc_kycprofile",
    "kyc_kycdocument",
    "kyc_kycverificationevent",
    "kyc_kycdocumentevent",
    "kyc_agreementlink",
    "leasing_lease",
    "leasing_leaselifecycleevent",
    "leasing_leasnotice",
    "leasing_leaserenewal",
    "leasing_leasecontractversion",
)


class Command(BaseCommand):
    help = "Disable PostgreSQL row-level security for workspace-owned domain tables."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Workspace RLS requires PostgreSQL.")

        with transaction.atomic():
            with connection.cursor() as cursor:
                for table in reversed(TABLES):
                    cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
                    cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

        self.stdout.write(self.style.WARNING("Workspace row-level security disabled."))
