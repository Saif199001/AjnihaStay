from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from workspaces.management.commands.enable_workspace_rls import POLICY_NAMES, TABLES


class LeasingRLSCoverageTests(TestCase):
    databases = {"default"}

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Leasing RLS coverage requires PostgreSQL.")

    def test_all_leasing_tables_are_in_the_canonical_rls_inventory(self):
        expected = {
            "leasing_lease",
            "leasing_leaselifecycleevent",
            "leasing_leasenotice",
            "leasing_leaserenewal",
            "leasing_leasecontractversion",
        }
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

    def test_workspace_visibility_function_covers_all_leasing_lifecycle_tables(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef('workspace_rls_row_visible(text,bigint)'::regprocedure)")
            definition = cursor.fetchone()[0]
        for table in (
            "leasing_leaselifecycleevent",
            "leasing_leasenotice",
            "leasing_leaserenewal",
            "leasing_leasecontractversion",
        ):
            self.assertIn(f"WHEN '{table}'", definition)
        self.assertIn("v_context_workspace_id", definition)

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
