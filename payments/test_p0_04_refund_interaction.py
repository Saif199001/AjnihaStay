from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from payments.ledger_models import FinancialLedgerEntry
from payments.models import AdvanceCredit, AdvanceCreditApplication, Invoice, PaymentAllocation
from payments.refund_service import request_payment_refund, transition_payment_refund
from payments.services import record_payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class P004RefundInteractionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("p004-refund-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="P0-04 Refund Workspace",
            slug="p0-04-refund-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P0-04 Refund Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="P004-1",
            rent=Decimal("10000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="P0-04 Refund Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 9, 30),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 1),
        )

    def refund_successfully(self, payment, amount):
        refund = request_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            payment=payment,
            amount=amount,
            reason="P0-04 interaction test",
        )
        transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status="processing",
        )
        return transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status="succeeded",
        )

    def test_successful_refund_reverses_payment_settlement_and_reopens_invoice(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": Decimal("10000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 3),
            },
        )
        self.refund_successfully(payment, Decimal("4000.00"))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("6000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(self.invoice.due_amount, Decimal("4000.00"))
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, Decimal("10000.00"))

    def test_failed_refund_does_not_change_invoice_settlement(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": Decimal("10000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 3),
            },
        )
        refund = request_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            payment=payment,
            amount=Decimal("4000.00"),
            reason="Provider rejected refund",
        )
        transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status="failed",
            failure_reason="Provider rejected refund",
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.due_amount, Decimal("0.00"))

    def test_overpayment_refund_consumes_allocation_before_advance_credit(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": Decimal("11000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 3),
            },
        )
        credit = AdvanceCredit.objects.get(source_payment=payment)
        self.assertEqual(credit.original_amount, Decimal("1000.00"))

        self.refund_successfully(payment, Decimal("500.00"))

        self.invoice.refresh_from_db()
        credit.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("9500.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(credit.available_amount, Decimal("1000.00"))

    def test_refund_can_reverse_applied_advance_credit_after_allocation_is_reversed(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": Decimal("11000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 3),
            },
        )
        credit = AdvanceCredit.objects.get(source_payment=payment)
        second_invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 10, 1),
            billing_end=date(2026, 10, 31),
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 11, 1),
        )
        from payments.advance_credit_service import apply_advance_credit

        application, remaining, _ = apply_advance_credit(
            self.owner,
            self.workspace,
            {"credit": credit.id, "invoice": second_invoice.id, "amount": Decimal("1000.00")},
        )
        self.assertEqual(application.amount, Decimal("1000.00"))
        self.assertEqual(remaining, Decimal("0.00"))

        ledger_entry = FinancialLedgerEntry.objects.get(
            event_type="advance_credit_applied",
            event_key=f"advance-credit-application:{application.pk}:created",
        )
        self.assertIsNone(ledger_entry.payment_id)
        self.assertEqual(ledger_entry.invoice_id, second_invoice.id)
        self.assertEqual(ledger_entry.metadata["source_payment_id"], payment.id)

        self.refund_successfully(payment, Decimal("10500.00"))

        self.invoice.refresh_from_db()
        second_invoice.refresh_from_db()
        credit.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")
        self.assertEqual(second_invoice.paid_amount, Decimal("500.00"))
        self.assertEqual(second_invoice.status, "partial")
        self.assertEqual(credit.available_amount, Decimal("0.00"))
        self.assertEqual(AdvanceCreditApplication.objects.filter(credit=credit).count(), 1)

    def test_pure_advance_refund_reduces_unconsumed_credit_only(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": None,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": Decimal("2000.00"),
                "payment_method": "bank",
                "payment_date": date(2026, 9, 3),
            },
        )
        credit = AdvanceCredit.objects.get(source_payment=payment)
        self.assertEqual(credit.available_amount, Decimal("2000.00"))

        self.refund_successfully(payment, Decimal("750.00"))

        credit.refresh_from_db()
        self.assertEqual(credit.available_amount, Decimal("1250.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")
