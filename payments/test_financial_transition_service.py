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
