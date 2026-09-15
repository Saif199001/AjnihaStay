from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.charge_service import create_charge
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .adjustment_service import create_financial_adjustment
from .advance_credit_service import apply_advance_credit, create_advance_credit
from .billing_models import BillingSchedule
from .final_settlement import FinalSettlement, finalize_final_settlement
from .late_fee_models import LateFee, LateFeePolicy
from .late_fee_service import generate_late_fee
from .ledger_models import FinancialLedgerEntry
from .models import Invoice, Payment
from .recurring_invoice_service import generate_invoice_from_schedule
from .refund_models import PaymentRefund
from .refund_service import request_payment_refund, transition_payment_refund
from .services import record_payment
from .allocation_service import allocate_payment


class P011CLedgerIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("p011c-owner@example.com", "ledger-test-password")
        self.workspace = Workspace.objects.create(
            name="P0.11C Workspace", slug="p011c-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P0.11C Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="501",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="P0.11C Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1),
            security_deposit=Decimal("5000.00"),
            deposit_paid=True,
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 9, 30),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 9, 30),
        )

    def ledger(self, event_key):
        return FinancialLedgerEntry.objects.get(event_key=event_key)

    def test_charge_generation_posts_ledger_event(self):
        charge = create_charge(
            self.owner,
            self.workspace,
            occupancy=self.occupancy,
            charge_type="maintenance",
            description="Ledger integration charge",
            amount=Decimal("250.00"),
            charge_date=date(2026, 9, 5),
        )
        entry = self.ledger(f"charge:{charge.pk}:generated")
        self.assertEqual(entry.event_type, "charge_generated")
        self.assertEqual(entry.amount, Decimal("250.00"))
        self.assertEqual(entry.occupancy_id, self.occupancy.id)

    def test_advance_credit_create_and_apply_post_ledger_events(self):
        payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("3000.00"),
            payment_method="upi",
            payment_date=date(2026, 9, 5),
            reference_id="P011C-ADV",
        )
        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": payment.id,
                "tenant": self.occupancy.tenant_id,
                "occupancy": self.occupancy.id,
                "amount": "2000.00",
            },
        )
        created_entry = self.ledger(f"advance-credit:{credit.pk}:created")
        self.assertEqual(created_entry.event_type, "advance_credit_created")
        self.assertEqual(created_entry.payment_id, payment.id)

        applied, remaining, _ = apply_advance_credit(
            self.owner,
            self.workspace,
            {"credit": credit.id, "invoice": self.invoice.id, "amount": "1000.00"},
        )
        applied_entry = self.ledger(f"advance-credit-application:{applied.pk}:created")
        self.assertEqual(applied_entry.event_type, "advance_credit_applied")
        self.assertEqual(applied_entry.payment_id, payment.id)
        self.assertEqual(applied_entry.invoice_id, self.invoice.id)
        self.assertEqual(remaining, Decimal("1000.00"))

    def test_adjustment_posts_ledger_event(self):
        adjustment, position, created = create_financial_adjustment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "adjustment_type": "credit",
                "amount": "500.00",
                "reason": "Ledger integration credit",
                "idempotency_key": "P011C-ADJ-1",
            },
        )
        entry = self.ledger(f"adjustment:{adjustment.pk}:created")
        self.assertTrue(created)
        self.assertEqual(entry.event_type, "adjustment_created")
        self.assertEqual(entry.invoice_id, self.invoice.id)
        self.assertEqual(position["outstanding"], Decimal("9500.00"))

    def test_late_fee_posts_ledger_event(self):
        policy = LateFeePolicy.objects.create(
            workspace=self.workspace,
            enabled=True,
            grace_period_days=0,
            calculation_mode=LateFeePolicy.MODE_FIXED,
            rate=Decimal("100.00"),
            minimum_overdue_balance=Decimal("0.01"),
        )
        late_fee, result = generate_late_fee(
            self.owner,
            self.workspace,
            self.invoice.id,
            as_of=date(2026, 10, 1),
        )
        self.assertTrue(result["created"])
        self.assertIsNotNone(late_fee)
        self.assertTrue(LateFee.objects.filter(pk=late_fee.pk).exists())
        entry = self.ledger(f"late-fee:{late_fee.pk}:generated")
        self.assertEqual(entry.event_type, "late_fee_generated")
        self.assertEqual(entry.invoice_id, self.invoice.id)
        self.assertEqual(entry.amount, Decimal("100.00"))
        self.assertEqual(policy.workspace_id, self.workspace.id)

    def test_recurring_invoice_posts_ledger_event(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy,
            frequency="monthly",
            amount=Decimal("10000.00"),
            next_run_date=date(2026, 9, 30),
            active=True,
        )
        invoice = generate_invoice_from_schedule(
            self.owner,
            self.workspace,
            schedule,
            billing_date=date(2026, 9, 30),
        )
        entry = self.ledger(f"recurring-invoice:{invoice.pk}:generated")
        self.assertEqual(entry.event_type, "recurring_invoice_generated")
        self.assertEqual(entry.invoice_id, invoice.id)
        self.assertEqual(entry.occupancy_id, self.occupancy.id)
        self.assertEqual(entry.amount, Decimal("10000.00"))
        self.assertTrue(FinancialLedgerEntry.objects.filter(event_type="charge_generated", invoice=invoice).exists())

    def _payment(self, amount="2000.00", reference="P011C-REFUND"):
        return Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal(amount),
            payment_method="upi",
            payment_date=date(2026, 9, 10),
            reference_id=reference,
        )

    def test_refund_request_and_transitions_post_ledger_events(self):
        payment = self._payment()
        refund = request_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            payment=payment,
            amount="500.00",
            reason="Customer refund",
            idempotency_key="P011C-REF-1",
        )
        requested = self.ledger(f"refund:{refund.pk}:requested")
        self.assertEqual(requested.event_type, "refund_requested")
        self.assertEqual(requested.payment_id, payment.id)

        refund = transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status=PaymentRefund.STATUS_PROCESSING,
        )
        processing = self.ledger(f"refund:{refund.pk}:processing")
        self.assertEqual(processing.event_type, "refund_processing")

        refund = transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status=PaymentRefund.STATUS_SUCCEEDED,
        )
        succeeded = self.ledger(f"refund:{refund.pk}:succeeded")
        self.assertEqual(succeeded.event_type, "refund_succeeded")
        self.assertEqual(succeeded.amount, Decimal("500.00"))

    def test_final_settlement_posts_ledger_event_without_creating_refund(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": "10000.00",
                "payment_method": "upi",
                "payment_date": date(2026, 9, 30),
                "reference_id": "P011C-SETTLE",
            },
        )
        self.assertEqual(payment.amount, Decimal("10000.00"))
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            self.occupancy.id,
            refundable_deposit="5000.00",
        )
        entry = self.ledger(f"final-settlement:{settlement.pk}:finalized")
        self.assertEqual(entry.event_type, "final_settlement_finalized")
        self.assertEqual(entry.occupancy_id, self.occupancy.id)
        self.assertFalse(PaymentRefund.objects.filter(payment=payment).exists())
        self.assertEqual(FinalSettlement.objects.count(), 1)

    def test_direct_payment_allocation_posts_ledger_event(self):
        source_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("1500.00"),
            payment_method="upi",
            payment_date=date(2026, 9, 10),
            reference_id="P011C-ALLOC",
        )
        target_invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 10, 1),
            billing_end=date(2026, 10, 31),
            rent_amount=Decimal("1500.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 31),
        )
        allocation = allocate_payment(
            self.owner,
            self.workspace,
            source_payment,
            [{"invoice": target_invoice.id, "amount": "1500.00"}],
        )
        entry = self.ledger(f"payment-allocation:{allocation[0].pk}:created")
        self.assertEqual(entry.event_type, "payment_allocated")
        self.assertEqual(entry.amount, Decimal("1500.00"))
        self.assertEqual(entry.payment_id, source_payment.id)
        self.assertEqual(entry.invoice_id, target_invoice.id)
