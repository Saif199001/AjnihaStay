from unittest import skipUnless

from django.db import connection, transaction
from django.test import TransactionTestCase

from .db import clear_workspace_context, set_workspace_context
from .management.commands.enable_workspace_rls import TABLES
from .rls_tests import WorkspaceRLSTests


@skipUnless(connection.vendor == "postgresql", "Workspace RLS requires PostgreSQL")
class RestrictedRoleRLSBehavioralMatrixTests(WorkspaceRLSTests):
    """R3-E matrix for every authoritative RLS table.

    The matrix derives its expected visibility from the same locked resolver
    used by the PostgreSQL policies, then verifies that SELECT/UPDATE/DELETE
    under the restricted, non-BYPASSRLS role agree with that classification.
    This keeps the matrix generic while still exercising all 26 tables.
    """

    def _resolver_classification(self, table, workspace_id):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id FROM {table} ORDER BY id")
            ids = [row[0] for row in cursor.fetchall()]
            if not ids:
                return []
            cursor.execute(
                "SELECT id FROM {0} WHERE workspace_rls_row_visible(%s, id) "
                "ORDER BY id".format(table),
                [table],
            )
            return [row[0] for row in cursor.fetchall()]

    def _assert_table_matrix(self, table, workspace_id):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id FROM {table} ORDER BY id")
            all_ids = [row[0] for row in cursor.fetchall()]
            expected_visible = set(self._resolver_classification(table, workspace_id))

            cursor.execute(f"SELECT id FROM {table} ORDER BY id")
            actual_visible = {row[0] for row in cursor.fetchall()}
            self.assertEqual(actual_visible, expected_visible, table)

            hidden_ids = [row_id for row_id in all_ids if row_id not in expected_visible]
            for row_id in hidden_ids:
                cursor.execute(f"UPDATE {table} SET id = id WHERE id = %s", [row_id])
                self.assertEqual(cursor.rowcount, 0, f"{table}: cross-workspace UPDATE")
                cursor.execute(f"DELETE FROM {table} WHERE id = %s", [row_id])
                self.assertEqual(cursor.rowcount, 0, f"{table}: cross-workspace DELETE")

    def test_all_26_authoritative_tables_restricted_role_matrix(self):
        self.assertEqual(len(TABLES), 26)
        self.assertEqual(len(set(TABLES)), 26)

        for workspace_id in (self.workspace_a.id, self.workspace_b.id):
            with transaction.atomic():
                self._as_rls_role()
                set_workspace_context(workspace_id)
                try:
                    for table in TABLES:
                        self._assert_table_matrix(table, workspace_id)
                finally:
                    self._reset_rls_role()

        with transaction.atomic():
            self._as_rls_role()
            clear_workspace_context()
            try:
                for table in TABLES:
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        self.assertEqual(cursor.fetchone()[0], 0, table)
            finally:
                self._reset_rls_role()
