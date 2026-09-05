from unittest import skipUnless

from django.db import connection, transaction
from django.test import TestCase

from accounts.models import User
from properties.models import Property

from .db import clear_workspace_context, set_workspace_context
from .models import Membership, Workspace


RLS_ROLE = "ajnihastay_rls_test"
RLS_TABLES = (
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


@skipUnless(connection.vendor == "postgresql", "Workspace RLS requires PostgreSQL")
class WorkspaceRLSHardeningTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
            cursor.execute(f"CREATE ROLE {RLS_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            for table in RLS_TABLES:
                cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {RLS_ROLE}")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute(f"DROP OWNED BY {RLS_ROLE}")
            cursor.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
        super().tearDownClass()

    def setUp(self):
        self.owner_a = User.objects.create_user("rls-hardening-a@example.com", "StrongPass123!")
        self.owner_b = User.objects.create_user("rls-hardening-b@example.com", "StrongPass123!")
        self.workspace_a = Workspace.objects.create(name="RLS Hardening A", slug="rls-hardening-a", owner=self.owner_a)
        self.workspace_b = Workspace.objects.create(name="RLS Hardening B", slug="rls-hardening-b", owner=self.owner_b)
        Membership.objects.create(workspace=self.workspace_a, user=self.owner_a, role="owner")
        Membership.objects.create(workspace=self.workspace_b, user=self.owner_b, role="owner")
        self.property_a = Property.objects.create(
            owner=self.owner_a,
            workspace=self.workspace_a,
            name="RLS Hardening Property A",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.property_b = Property.objects.create(
            owner=self.owner_b,
            workspace=self.workspace_b,
            name="RLS Hardening Property B",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110002",
        )

    def _as_rls_role(self):
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {RLS_ROLE}")

    def test_missing_workspace_context_fails_closed_without_cast_error(self):
        with transaction.atomic():
            self._as_rls_role()
            clear_workspace_context()
            rows = list(Property.objects.values_list("id", "workspace_id"))
        self.assertEqual(rows, [])

    def test_workspace_context_only_exposes_matching_workspace(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            rows = list(Property.objects.order_by("id").values_list("id", "workspace_id"))
        self.assertEqual(rows, [(self.property_a.id, self.workspace_a.id)])

    def test_wrong_workspace_context_hides_existing_rows(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_b.id)
            rows = list(Property.objects.filter(id=self.property_a.id).values_list("id", "workspace_id"))
        self.assertEqual(rows, [])
