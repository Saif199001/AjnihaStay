from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from payments.allocation_service import allocate_payment
from payments.models import Payment, PaymentAllocation
from payments.tests import PaymentIntegrityTests


class PaymentAllocationAtomicEdgeTests(PaymentIntegrityTests):
    def test_rejected_multi_invoice_request_is_atomic(self):
        payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000"), payment_method="upi", payment_date=self.invoice.billing_start)
        with self.assertRaises(ValidationError):
            allocate_payment(self.owner, self.workspace, payment, [
                {"invoice": self.invoice.id, "amount": "1000"},
                {"invoice": 999999, "amount": "1000"},
            ])
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0"))
        self.assertEqual(self.invoice.status, "pending")

    def test_incremental_allocation_reaches_exact_boundaries(self):
        payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000"), payment_method="upi", payment_date=self.invoice.billing_start)
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice.id, "amount": "4000"}])
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice, "amount": "6000"}])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("10000"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(payment.unallocated_amount, Decimal("0"))
