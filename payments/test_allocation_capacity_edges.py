from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from payments.allocation_service import allocate_payment
from payments.models import Payment
from payments.tests import PaymentIntegrityTests


class PaymentAllocationCapacityEdgeTests(PaymentIntegrityTests):
    def test_payment_capacity_accounts_for_existing_allocations(self):
        payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000"), payment_method="upi", payment_date=self.invoice.billing_start)
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice.id, "amount": "6000"}])
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds payment amount"):
            allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice.id, "amount": "4001"}])
        self.assertEqual(payment.unallocated_amount, Decimal("4000"))

    def test_invoice_capacity_is_enforced_across_payments(self):
        payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000"), payment_method="upi", payment_date=self.invoice.billing_start)
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": self.invoice.id, "amount": "10000"}])
        second = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("1000"), payment_method="cash", payment_date=self.invoice.billing_start)
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds invoice remaining amount"):
            allocate_payment(self.owner, self.workspace, second, [{"invoice": self.invoice.id, "amount": "1"}])
