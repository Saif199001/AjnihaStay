from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from payments.advance_credit_service import get_advance_credit_available_amount
from payments.models import AdvanceCredit, PaymentAllocation
from payments.serializers import PaymentSerializer
from payments.services import record_payment

from .test_advance_credit_service import AdvanceCreditServiceTests


class P004PaymentIntakeTests(AdvanceCreditServiceTests):
    def test_exact_payment_still_settles_invoice(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {"invoice": self.invoice.id, "amount": "10000.00", "payment_method": "bank", "payment_date": self.payment.payment_date},
        )
        self.invoice.refresh_from_db()
        self.assertEqual(payment.invoice_id, self.invoice.id)
        self.assertEqual(payment.amount, Decimal("10000.00"))
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")

    def test_partial_payment_still_settles_only_received_amount(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {"invoice": self.invoice.id, "amount": "4000.00", "payment_method": "bank", "payment_date": self.payment.payment_date},
        )
        self.invoice.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("4000.00"))
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(self.invoice.due_amount, Decimal("6000.00"))

    def test_overpayment_settles_invoice_and_creates_credit_for_excess(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {"invoice": self.invoice.id, "amount": "12500.00", "payment_method": "bank", "payment_date": self.payment.payment_date},
        )
        self.invoice.refresh_from_db()
        credit = AdvanceCredit.objects.get(source_payment=payment)
        self.assertEqual(payment.invoice_id, self.invoice.id)
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, Decimal("10000.00"))
        self.assertEqual(credit.original_amount, Decimal("2500.00"))
        self.assertEqual(get_advance_credit_available_amount(credit), Decimal("2500.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.due_amount, Decimal("0.00"))

    def test_pure_advance_creates_unlinked_payment_and_credit(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "amount": "7500.00",
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "payment_method": "bank",
                "payment_date": self.payment.payment_date,
            },
        )
        credit = AdvanceCredit.objects.get(source_payment=payment)
        self.assertIsNone(payment.invoice_id)
        self.assertEqual(credit.tenant_id, self.tenant.id)
        self.assertEqual(credit.occupancy_id, self.occupancy.id)
        self.assertEqual(credit.original_amount, Decimal("7500.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))

    def test_pure_advance_requires_tenant(self):
        with self.assertRaisesMessage(ValidationError, "Tenant is required for an advance payment"):
            record_payment(
                self.owner,
                self.workspace,
                {"amount": "7500.00", "payment_method": "bank", "payment_date": self.payment.payment_date},
            )

    def test_pure_advance_serializer_requires_tenant(self):
        serializer = PaymentSerializer(
            data={"invoice": None, "amount": "7500.00", "payment_method": "bank", "payment_date": self.payment.payment_date}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("tenant", serializer.errors)

    def test_invoice_overpayment_is_atomic_when_advance_credit_creation_fails(self):
        # A second credit for the same source payment is impossible, so force
        # a tenant validation failure before the transaction can commit.
        with self.assertRaisesMessage(ValidationError, "Advance credit tenant must match the payment invoice tenant"):
            record_payment(
                self.owner,
                self.workspace,
                {
                    "invoice": self.invoice.id,
                    "amount": "12500.00",
                    "tenant": self.tenant.id + 999999,
                    "payment_method": "bank",
                    "payment_date": self.payment.payment_date,
                },
            )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")
