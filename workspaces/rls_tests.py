from django.db import connection, transaction
from django.test import TestCase, skipUnless

from accounts.models import User
from properties.models import Property

from .db import clear_workspace_context, set_workspace_context
from .models import Membership, Workspace


RLS_ROLE = "ajnihastay_rls_test"
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


@skipUnless(connection.vendor == "postgresql", "Workspace RLS requires PostgreSQL")
class WorkspaceRLSTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
            cursor.execute(f"CREATE ROLE {RLS_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            for table in PROTECTED_TABLES:
                cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {RLS_ROLE}")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
        super().tearDownClass()

    def setUp(self):
        self.owner_a = User.objects.create_user("rls-a@example.com", "StrongPass123!")
        self.owner_b = User.objects.create_user("rls-b@example.com", "StrongPass123!")
        self.workspace_a = Workspace.objects.create(name="RLS A", slug="rls-a", owner=self.owner_a)
        self.workspace_b = Workspace.objects.create(name="RLS B", slug="rls-b", owner=self.owner_b)
        Membership.objects.create(workspace=self.workspace_a, user=self.owner_a, role="owner")
        Membership.objects.create(workspace=self.workspace_b, user=self.owner_b, role="owner")
        self.property_a = Property.objects.create(
            owner=self.owner_a,
            workspace=self.workspace_a,
            name="RLS Property A",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.property_b = Property.objects.create(
            owner=self.owner_b,
            workspace=self.workspace_b,
            name="RLS Property B",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110002",
        )

    def _as_rls_role(self):
        connection.cursor().execute(f"SET LOCAL ROLE {RLS_ROLE}")

    def test_all_protected_tables_are_rls_enabled_and_forced(self):
        with connection.cursor() as cursor:
            for table in PROTECTED_TABLES:
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = %s::regclass",
                    [table],
                )
                enabled, forced = cursor.fetchone()
                self.assertTrue(enabled, table)
                self.assertTrue(forced, table)

                cursor.execute(
                    "SELECT COUNT(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = %s",
                    [table.split(".")[-1]],
                )
                self.assertGreater(cursor.fetchone()[0], 0, table)

    def test_rls_hides_other_workspace_without_application_filter(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            rows = list(Property.objects.order_by("id").values_list("id", "workspace_id"))

        self.assertEqual(rows, [(self.property_a.id, self.workspace_a.id)])

    def test_rls_hides_all_workspace_data_without_context(self):
        with transaction.atomic():
            self._as_rls_role()
            clear_workspace_context()
            rows = list(Property.objects.values_list("id", "workspace_id"))

        self.assertEqual(rows, [])

    def test_rls_blocks_cross_workspace_insert(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            with self.assertRaises(Exception):
                Property.objects.create(
                    owner=self.owner_b,
                    workspace=self.workspace_b,
                    name="Blocked Cross Workspace",
                    property_type="pg",
                    address="Delhi",
                    city="Delhi",
                    state="Delhi",
                    pincode="110003",
                )

    def test_rls_blocks_cross_workspace_update(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            updated = Property.objects.filter(id=self.property_b.id).update(name="Blocked Update")

        self.assertEqual(updated, 0)
        self.property_b.refresh_from_db()
        self.assertEqual(self.property_b.name, "RLS Property B")
