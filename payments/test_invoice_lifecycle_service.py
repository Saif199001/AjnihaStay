from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .invoice_lifecycle_service import get_invoice_lifecycle


class InvoiceLifecycleP05Tests(SimpleTestCase):
    def _invoice(self, due_date=date(2026, 9, 10)):
        return SimpleNamespace(due_date=due_date)

    @patch("payments.invoice_lifecycle_service.calculate_invoice_financial_position")
    def test_pending_invoice_is_not_overdue_on_due_date(self, position):
        position.return_value = {
            "status": "pending",
            "outstanding": Decimal("100.00"),
            "settlement": Decimal("0.00"),
        }
        result = get_invoice_lifecycle(self._invoice(), as_of=date(2026, 9, 10))
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["overdue"])
        self.assertEqual(result["outstanding"], Decimal("100.00"))

    @patch("payments.invoice_lifecycle_service.calculate_invoice_financial_position")
    def test_outstanding_invoice_becomes_overdue_after_due_date(self, position):
        position.return_value = {
            "status": "partial",
            "outstanding": Decimal("40.00"),
            "settlement": Decimal("60.00"),
        }
        result = get_invoice_lifecycle(self._invoice(), as_of=date(2026, 9, 11))
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["overdue"])

    @patch("payments.invoice_lifecycle_service.calculate_invoice_financial_position")
    def test_paid_invoice_is_never_overdue(self, position):
        position.return_value = {
            "status": "paid",
            "outstanding": Decimal("0.00"),
            "settlement": Decimal("100.00"),
        }
        result = get_invoice_lifecycle(self._invoice(), as_of=date(2026, 9, 30))
        self.assertEqual(result["status"], "paid")
        self.assertFalse(result["overdue"])

    @patch("payments.invoice_lifecycle_service.calculate_invoice_financial_position")
    def test_invalid_status_is_rejected(self, position):
        position.return_value = {
            "status": "void",
            "outstanding": Decimal("0.00"),
            "settlement": Decimal("0.00"),
        }
        with self.assertRaises(ValidationError):
            get_invoice_lifecycle(self._invoice())
