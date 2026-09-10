from django.test import SimpleTestCase

from payments.financial_transition_service import FinancialTransition, transition_name


class FinancialTransitionContractTests(SimpleTestCase):
    def test_all_supported_mutations_have_stable_transition_names(self):
        expected = {
            "create_invoice",
            "record_payment",
            "allocate_payment",
            "create_advance_credit",
            "apply_advance_credit",
            "create_adjustment",
            "create_billing_schedule",
            "update_billing_schedule",
            "generate_charge",
        }
        self.assertEqual({transition.value for transition in FinancialTransition}, expected)
        for transition in FinancialTransition:
            self.assertEqual(transition_name(transition), transition.value)
            self.assertEqual(transition_name(transition.value), transition.value)

    def test_unknown_transition_is_rejected(self):
        with self.assertRaises(ValueError):
            transition_name("not_a_financial_transition")
