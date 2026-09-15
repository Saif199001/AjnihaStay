from django.test import SimpleTestCase

from .financial_transition_service import FinancialTransition, transition_name


class FinancialTransitionP04Tests(SimpleTestCase):
    def test_recurring_invoice_transition_is_registered(self):
        self.assertEqual(
            transition_name(FinancialTransition.GENERATE_RECURRING_INVOICE),
            "generate_recurring_invoice",
        )
        self.assertEqual(
            transition_name("generate_recurring_invoice"),
            "generate_recurring_invoice",
        )


class FinancialTransitionP05Tests(SimpleTestCase):
    def test_invoice_lifecycle_transition_is_registered(self):
        self.assertEqual(
            transition_name(FinancialTransition.REFRESH_INVOICE_LIFECYCLE),
            "refresh_invoice_lifecycle",
        )
        self.assertEqual(
            transition_name("refresh_invoice_lifecycle"),
            "refresh_invoice_lifecycle",
        )
