from decimal import Decimal

from django.db import connection, transaction

from .rls_tests import WorkspaceRLSTests
from .db import set_workspace_context


class PaymentAllocationRLSIsolationTests(WorkspaceRLSTests):
    def test_rls_blocks_mixed_workspace_payment_and_invoice(self):
        with transaction.atomic():
            self._as_rls_role()
            set_workspace_context(self.workspace_a.id)
            with self.assertRaises(Exception):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO payments_paymentallocation "
                            "(id, payment_id, invoice_id, amount, created_at) "
                            "VALUES (%s, %s, %s, %s, NOW())",
                            [
                                self.allocation_b.id + 2000000,
                                self.payment_a.id,
                                self.invoice_b.id,
                                Decimal("100.00"),
                            ],
                        )
            self._reset_rls_role()
