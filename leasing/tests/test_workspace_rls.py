from importlib import import_module

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from workspaces.management.commands.enable_workspace_rls import POLICY_NAMES, TABLES


LIFECYCLE_TABLES = {
    "leasing_leaselifecycleevent",
    "leasing_leasenotice",
    "leasing_leaserenewal",
    "leasing_leasecontractversion",
}
LIFECYCLE_LEASE_LINKS = {
    "leasing_leaselifecycleevent": "lease_id",
    "leasing_leasenotice": "lease_id",
    "leasing_leaserenewal": "source_lease_id",
    "leasing_leasecontractversion": "lease_id",
}


class LeasingRLSCoverageTests(TestCase):
    databases = {"default"}

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Leasing RLS coverage requires PostgreSQL.")

    def test_all_leasing_tables_are_in_the_canonical_rls_inventory(self):
        expected = {"leasing_lease"} | LIFECYCLE_TABLES
        self.assertTrue(expected.issubset(set(TABLES)))

    def test_all_leasing_tables_have_forced_rls_and_one_canonical_policy(self):
        expected = {
            table.split(".")[-1]: POLICY_NAMES[table]
            for table in TABLES
            if table.startswith("leasing_")
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = ANY(%s)
                """,
                [list(expected)],
            )
            relations = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
            self.assertEqual(set(relations), set(expected))
            for table, (enabled, forced) in relations.items():
                self.assertTrue(enabled, f"{table} must have RLS enabled")
                self.assertTrue(forced, f"{table} must have FORCE RLS enabled")

            cursor.execute(
                """
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = ANY(%s)
                ORDER BY tablename, policyname
                """,
                [list(expected)],
            )
            actual = {}
            for table, policy in cursor.fetchall():
                actual.setdefault(table, []).append(policy)
        for table, policy in expected.items():
            self.assertEqual(actual.get(table), [policy], f"{table} must have only its canonical RLS policy")

    def test_canonical_policies_delegate_to_workspace_visibility_function(self):
        call_command("enable_workspace_rls", verbosity=0)
        expected = {
            table.split(".")[-1]: POLICY_NAMES[table]
            for table in TABLES
            if table.startswith("leasing_")
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename, policyname, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = ANY(%s)
                """,
                [list(expected)],
            )
            policies = {table: (name, qual or "", with_check or "") for table, name, qual, with_check in cursor.fetchall()}
        for table, policy_name in expected.items():
            name, qual, with_check = policies[table]
            self.assertEqual(name, policy_name)
            self.assertIn("workspace_rls_row_visible", qual, f"{table} SELECT/UPDATE/DELETE policy must use canonical visibility")
            self.assertIn("workspace_rls_row_visible", with_check, f"{table} INSERT/UPDATE policy must use canonical visibility")

    def test_workspace_visibility_function_checks_lease_workspace_relationships(self):
        call_command("enable_workspace_rls", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef('workspace_rls_row_visible(text,bigint)'::regprocedure)")
            definition = cursor.fetchone()[0]
        for table, lease_fk in LIFECYCLE_LEASE_LINKS.items():
            self.assertIn(f"WHEN '{table}'", definition)
            self.assertIn(f"JOIN leasing_lease l ON l.id = ", definition)
            self.assertIn(f"{lease_fk}", definition)
            self.assertIn("workspace_id = l.workspace_id", definition)

    def test_migration_policies_are_relational_and_use_the_correct_lease_foreign_key(self):
        migration = import_module("leasing.migrations.0008_normalize_lifecycle_rls_policies")
        configured = {
            table: lease_fk
            for table, _canonical_name, _legacy_name, lease_fk in migration.TABLE_POLICIES
        }
        self.assertEqual(configured, LIFECYCLE_LEASE_LINKS)

        # Guard the migration's forward policy against regressing to workspace_id-only
        # checks; the migration must remain safe before the central command is run.
        import inspect

        source = inspect.getsource(migration.normalize_policy_names)
        self.assertIn("parent_lease.workspace_id", source)
        self.assertIn("relationship_check", source)
        self.assertIn("WITH CHECK", source)
        self.assertIn("USING", source)

    def test_rls_enable_command_is_idempotent_after_migration_normalization(self):
        call_command("enable_workspace_rls", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = ANY(%s)
                ORDER BY tablename, policyname
                """,
                [[table.split(".")[-1] for table in TABLES if table.startswith("leasing_")]],
            )
            rows = cursor.fetchall()
        self.assertEqual(len(rows), len([table for table in TABLES if table.startswith("leasing_")]))
