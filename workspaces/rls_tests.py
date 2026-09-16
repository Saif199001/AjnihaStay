from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.core.management import call_command, CommandError
from django.db import connection, transaction
from django.test import TransactionTestCase

from accounts.models import User
from payments.models import Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit

from .db import clear_workspace_context, set_workspace_context
from .management.commands.enable_workspace_rls import (
    POLICIES,
    POLICY_NAMES,
    RLS_FUNCTION_OWNER,
    TABLES,
)
from .models import Membership, Workspace


RLS_ROLE = "ajnihastay_rls_test"


@skipUnless(connection.vendor == "postgresql", "Workspace RLS requires PostgreSQL")
class WorkspaceRLSTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("enable_workspace_rls", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
            cursor.execute(f"CREATE ROLE {RLS_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            for table in TABLES:
                cursor.execute(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {RLS_ROLE}"
                )
            cursor.execute(
                f"GRANT SELECT ON TABLE accounts_user, workspaces_workspace, workspaces_membership TO {RLS_ROLE}"
            )
            cursor.execute(
                f"GRANT USAGE, SELECT ON SEQUENCE properties_property_id_seq TO {RLS_ROLE}"
            )
            cursor.execute(
                "GRANT EXECUTE ON FUNCTION workspace_rls_row_visible(text, bigint) "
                f"TO {RLS_ROLE}"
            )

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {RLS_ROLE}")
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
            owner=self.owner_a, workspace=self.workspace_a, name="RLS Property A",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        self.property_b = Property.objects.create(
            owner=self.owner_b, workspace=self.workspace_b, name="RLS Property B",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110002",
        )
        self.tenant_a = Tenant.objects.create(
            owner=self.owner_a, workspace=self.workspace_a, full_name="RLS Tenant A",
            phone="9000000001", permanent_address="Delhi",
        )
        self.unit_a = Unit.objects.create(property=self.property_a, unit_type="room", unit_number="A-1", rent=Decimal("5000.00"))
        self.occupancy_a = Occupancy.objects.create(
            tenant=self.tenant_a, unit=self.unit_a, allotted_by=self.owner_a, rent=Decimal("5000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1), billing_type="arrears", billing_cycle="monthly",
        )
        self.invoice_a = Invoice.objects.create(
            occupancy=self.occupancy_a, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal("5000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 5),
        )
        self.payment_a = Payment.objects.create(
            workspace=self.workspace_a, invoice=None, amount=Decimal("1000.00"), payment_method="upi", payment_date=date(2026, 9, 7),
        )
        self.allocation_a = PaymentAllocation.objects.create(payment=self.payment_a, invoice=self.invoice_a, amount=Decimal("500.00"))
        self.tenant_b = Tenant.objects.create(
            owner=self.owner_b, workspace=self.workspace_b, full_name="RLS Tenant B", phone="9000000002", permanent_address="Delhi",
        )
        self.unit_b = Unit.objects.create(property=self.property_b, unit_type="room", unit_number="B-1", rent=Decimal("5000.00"))
        self.occupancy_b = Occupancy.objects.create(
            tenant=self.tenant_b, unit=self.unit_b, allotted_by=self.owner_b, rent=Decimal("5000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1), billing_type="arrears", billing_cycle="monthly",
        )
        self.invoice_b = Invoice.objects.create(
            occupancy=self.occupancy_b, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal("5000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 5),
        )
        self.payment_b = Payment.objects.create(
            workspace=self.workspace_b, invoice=None, amount=Decimal("1000.00"), payment_method="upi", payment_date=date(2026, 9, 7),
        )
        self.allocation_b = PaymentAllocation.objects.create(payment=self.payment_b, invoice=self.invoice_b, amount=Decimal("500.00"))

    def _as_rls_role(self):
        connection.cursor().execute(f"SET ROLE {RLS_ROLE}")

    def _reset_rls_role(self):
        connection.cursor().execute("RESET ROLE")

    def test_rls_role_is_not_superuser_or_bypassrls(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", [RLS_ROLE])
            is_superuser, bypass_rls = cursor.fetchone()
        self.assertFalse(is_superuser)
        self.assertFalse(bypass_rls)

    def test_rls_resolver_has_dedicated_non_login_capability_owner(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.prosecdef, r.rolname, r.rolsuper, r.rolbypassrls, r.rolcanlogin, r.rolcreatedb, r.rolcreaterole, r.rolinherit, r.rolreplication "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_roles r ON r.oid = p.proowner "
                "WHERE n.nspname = 'public' AND p.proname = %s AND pg_get_function_identity_arguments(p.oid) = %s",
                ["workspace_rls_row_visible", "p_table text, p_id bigint"],
            )
            row = cursor.fetchone()
        self.assertIsNotNone(row)
        security_definer, owner, superuser, bypass_rls, can_login, createdb, createrole, inherit, replication = row
        self.assertTrue(security_definer)
        self.assertEqual(owner, RLS_FUNCTION_OWNER)
        self.assertFalse(superuser)
        self.assertTrue(bypass_rls)
        self.assertFalse(can_login)
        self.assertFalse(createdb)
        self.assertFalse(createrole)
        self.assertFalse(inherit)
        self.assertFalse(replication)

    def test_rls_resolver_executes_for_restricted_non_bypass_caller(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT workspace_rls_row_visible(%s, %s), workspace_rls_row_visible(%s, %s)",
                    ["properties_property", self.property_a.id, "properties_property", self.property_b.id],
                )
                visible_a, visible_b = cursor.fetchone()
            self._reset_rls_role()
        self.assertTrue(visible_a)
        self.assertFalse(visible_b)

    def test_rls_resolver_is_not_publicly_executable(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_function_privilege('public', %s, 'EXECUTE')", ["workspace_rls_row_visible(text,bigint)"])
            public_execute = cursor.fetchone()[0]
        self.assertFalse(public_execute)

    def test_rls_resolver_runtime_role_has_explicit_execute(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_function_privilege(current_user, %s, 'EXECUTE')", ["workspace_rls_row_visible(text,bigint)"])
            current_user_execute = cursor.fetchone()[0]
        self.assertTrue(current_user_execute)

    def test_resolver_owner_has_select_only_on_authoritative_tables(self):
        with connection.cursor() as cursor:
            for table in TABLES:
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    cursor.execute("SELECT has_table_privilege(%s, %s, %s)", [RLS_FUNCTION_OWNER, table, privilege])
                    allowed = cursor.fetchone()[0]
                    if privilege == "SELECT":
                        self.assertTrue(allowed, f"{table}: {privilege}")
                    else:
                        self.assertFalse(allowed, f"{table}: {privilege}")

    def test_authoritative_inventory_is_fully_rls_enabled_forced_and_policied(self):
        with connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = %s::regclass", [table])
                enabled, forced = cursor.fetchone()
                self.assertTrue(enabled, table)
                self.assertTrue(forced, table)
                cursor.execute("SELECT policyname, qual, with_check FROM pg_policies WHERE schemaname = 'public' AND tablename = %s", [table.split(".")[-1]])
                policies = cursor.fetchall()
                self.assertTrue(any(row[0] == POLICY_NAMES[table] for row in policies), table)
                policy = next(row for row in policies if row[0] == POLICY_NAMES[table])
                self.assertIsNotNone(policy[1], table)
                self.assertIsNotNone(policy[2], table)
        self.assertEqual(set(TABLES), set(POLICIES))

    def test_unexpected_authoritative_policy_is_detected_before_sync(self):
        table = "properties_property"
        unexpected_policy = "unexpected_workspace_policy"
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE POLICY {unexpected_policy} ON {table} USING (true) WITH CHECK (true)")
            try:
                cursor.execute("SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public' AND tablename = %s", [table])
                self.assertIn((table, unexpected_policy), cursor.fetchall())
                with self.assertRaises(CommandError) as context:
                    call_command("enable_workspace_rls", verbosity=0)
                self.assertIn(unexpected_policy, str(context.exception))
            finally:
                cursor.execute(f"DROP POLICY IF EXISTS {unexpected_policy} ON {table}")
        call_command("enable_workspace_rls", verbosity=0)

    def test_rls_hides_other_workspace_without_application_filter(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            rows = list(Property.objects.order_by("id").values_list("id", "workspace_id"))
            self._reset_rls_role()
        self.assertEqual(rows, [(self.property_a.id, self.workspace_a.id)])

    def test_rls_hides_all_workspace_data_without_context(self):
        with transaction.atomic():
            self._as_rls_role(); clear_workspace_context()
            rows = list(Property.objects.values_list("id", "workspace_id"))
            payments = list(Payment.objects.values_list("id", "workspace_id"))
            allocations = list(PaymentAllocation.objects.values_list("id", "payment_id"))
            self._reset_rls_role()
        self.assertEqual(rows, []); self.assertEqual(payments, []); self.assertEqual(allocations, [])

    def test_payment_rls_uses_explicit_workspace_for_pure_advance(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            rows = list(Payment.objects.order_by("id").values_list("id", "workspace_id", "invoice_id"))
            self._reset_rls_role()
        self.assertEqual(rows, [(self.payment_a.id, self.workspace_a.id, None)])

    def test_payment_allocation_rls_hides_other_workspace(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            rows = list(PaymentAllocation.objects.order_by("id").values_list("id", "payment_id"))
            self._reset_rls_role()
        self.assertEqual(rows, [(self.allocation_a.id, self.payment_a.id)])

    def test_rls_blocks_cross_workspace_insert(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            with self.assertRaises(Exception):
                with transaction.atomic():
                    Property.objects.create(owner=self.owner_b, workspace=self.workspace_b, name="Blocked Cross Workspace", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110003")
            self._reset_rls_role()

    def test_rls_blocks_cross_workspace_payment_allocation_insert(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            with self.assertRaises(Exception):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("INSERT INTO payments_paymentallocation (id, payment_id, invoice_id, amount, created_at) VALUES (%s, %s, %s, %s, NOW())", [self.allocation_b.id + 1000000, self.payment_b.id, self.invoice_a.id, Decimal("100.00")])
            self._reset_rls_role()

    def test_rls_blocks_cross_workspace_update(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            updated = Property.objects.filter(id=self.property_b.id).update(name="Blocked Update")
            self._reset_rls_role()
        self.assertEqual(updated, 0)
        self.property_b.refresh_from_db()
        self.assertEqual(self.property_b.name, "RLS Property B")

    def test_rls_blocks_cross_workspace_delete(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            deleted, _ = Property.objects.filter(id=self.property_b.id).delete()
            self._reset_rls_role()
        self.assertEqual(deleted, 0)
        self.assertTrue(Property.objects.filter(id=self.property_b.id).exists())

    def test_rls_blocks_cross_workspace_payment_allocation_delete(self):
        with transaction.atomic():
            self._as_rls_role(); set_workspace_context(self.workspace_a.id)
            deleted, _ = PaymentAllocation.objects.filter(id=self.allocation_b.id).delete()
            self._reset_rls_role()
        self.assertEqual(deleted, 0)
        self.assertTrue(PaymentAllocation.objects.filter(id=self.allocation_b.id).exists())

    def test_rls_blocks_delete_without_workspace_context(self):
        with transaction.atomic():
            self._as_rls_role(); clear_workspace_context()
            deleted, _ = Property.objects.filter(id=self.property_a.id).delete()
            self._reset_rls_role()
        self.assertEqual(deleted, 0)
        self.assertTrue(Property.objects.filter(id=self.property_a.id).exists())
