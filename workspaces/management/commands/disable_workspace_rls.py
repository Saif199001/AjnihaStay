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
