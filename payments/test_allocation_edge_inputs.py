from django.core.exceptions import ValidationError
from django.test import TestCase

from payments.allocation_service import allocate_payment
from payments.models import Payment
from payments.tests import PaymentIntegrityTests


class PaymentAllocationInputEdgeTests(PaymentIntegrityTests):
    def test_rejects_empty_and_malformed_requests(self):
        payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount="1000.00",
            payment_method="upi",
            payment_date=self.invoice.billing_start,
        )
        with self.assertRaisesMessage(ValidationError, "At least one invoice allocation is required"):
            allocate_payment(self.owner, self.workspace, payment, [])
        with self.assertRaisesMessage(ValidationError, "Invalid allocation entry"):
            allocate_payment(self.owner, self.workspace, payment, [None])

    def test_rejects_invalid_ids_and_amounts(self):
        payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount="1000.00",
            payment_method="upi",
            payment_date=self.invoice.billing_start,
        )
        for invoice_id in (None, 0, -1, "bad"):
            with self.subTest(invoice_id=invoice_id), self.assertRaises(ValidationError):
                allocate_payment(self.owner, self.workspace, payment, [{"invoice": invoice_id, "amount": "1000"}])
        for amount in ("0", "-1", "bad", "NaN", "Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice.id, "amount": amount}])
