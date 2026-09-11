from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .adjustment_service import create_financial_adjustment
from .allocation_service import allocate_payment
from .ledger_service import post_ledger_event
from .models import Invoice, Payment
from .reporting import aging_report, collection_period_report


class P012CPeriodAgingRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("p012c-owner@example.com", "p012c-password")
        self.other_owner = User.objects.create_user("p012c-other@example.com", "p012c-password")
        self.workspace = Workspace.objects.create(name="P012C Workspace", slug="p012c-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other P012C Workspace", slug="other-p012c-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="P012C Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="701", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="P012C Tenant", phone="9999999998", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("12000.00"),
            check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31),
            next_due_date=date(2027, 1, 1), security_deposit=Decimal("5000.00"), deposit_paid=True,
        )
        self.as_of = date(2026, 9, 30)

    def invoice(self, *, due_date, amount="100.00"):
        return Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal(amount), charges_amount=Decimal("0.00"), due_date=due_date,
        )

    def test_aging_exact_boundaries_and_future_due_are_classified(self):
        cases = {
            "current": date(2026, 10, 1),
            "1_30": date(2026, 9, 29),
            "31_60": date(2026, 8, 30),
            "61_90": date(2026, 7, 2),
            "90_plus": date(2026, 7, 1),
        }
        invoices = {bucket: self.invoice(due_date=due) for bucket, due in cases.items()}
        report = aging_report(workspace=self.workspace, as_of=self.as_of)
        self.assertEqual(report["invoice_count"], 5)
        for bucket, invoice in invoices.items():
            self.assertEqual(report["buckets"][bucket]["count"], 1)
            self.assertEqual(report["buckets"][bucket]["invoices"][0]["invoice_id"], invoice.pk)
            self.assertEqual(report["buckets"][bucket]["invoices"][0]["outstanding"], Decimal("100.00"))
        self.assertEqual(report["buckets"]["current"]["invoices"][0]["days_overdue"], 0)
        self.assertEqual(report["buckets"]["1_30"]["invoices"][0]["days_overdue"], 1)
        self.assertEqual(report["buckets"]["31_60"]["invoices"][0]["days_overdue"], 31)
        self.assertEqual(report["buckets"]["61_90"]["invoices"][0]["days_overdue"], 90)
        self.assertEqual(report["buckets"]["90_plus"]["invoices"][0]["days_overdue"], 91)

    def test_aging_excludes_fully_settled_invoice(self):
        invoice = self.invoice(due_date=date(2026, 9, 1))
        payment = Payment.objects.create(
            workspace=self.workspace, amount=Decimal("100.00"), payment_method="upi", payment_date=date(2026, 9, 15),
        )
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": invoice.id, "amount": "100.00"}])
        report = aging_report(workspace=self.workspace, as_of=self.as_of)
        self.assertEqual(report["invoice_count"], 0)
        self.assertEqual(report["total_outstanding"], Decimal("0.00"))

    def test_aging_uses_canonical_partial_adjustment_and_late_fee_position(self):
        invoice = self.invoice(due_date=date(2026, 9, 1), amount="1000.00")
        payment = Payment.objects.create(
            workspace=self.workspace, amount=Decimal("400.00"), payment_method="cash", payment_date=date(2026, 9, 10),
        )
        allocate_payment(self.owner, self.workspace, payment, [{"invoice": invoice.id, "amount": "400.00"}])
        create_financial_adjustment(
            self.owner, self.workspace,
            {"invoice": invoice.id, "adjustment_type": "debit", "amount": "100.00", "reason": "late service charge", "idempotency_key": "p012c-debit-1"},
        )
        from .late_fee_models import LateFee, LateFeePolicy
        policy = LateFeePolicy.objects.create(
            workspace=self.workspace, enabled=True, calculation_mode=LateFeePolicy.MODE_FIXED,
            rate=Decimal("50.00"), minimum_overdue_balance=Decimal("0.01"), grace_period_days=0,
        )
        LateFee.objects.create(
            workspace=self.workspace, invoice=invoice, policy=policy, effective_date=date(2026, 9, 30),
            amount=Decimal("50.00"), outstanding_balance=Decimal("600.00"), calculation_mode=LateFeePolicy.MODE_FIXED,
            reason="test late fee", created_by=self.owner,
        )
        report = aging_report(workspace=self.workspace, as_of=self.as_of)
        row = report["buckets"]["1_30"]["invoices"][0]
        self.assertEqual(row["outstanding"], Decimal("750.00"))
        self.assertEqual(report["total_outstanding"], Decimal("750.00"))

    def test_collection_period_is_inclusive_for_payment_date_and_refund_event_date(self):
        Payment.objects.create(workspace=self.workspace, amount=Decimal("100.00"), payment_method="cash", payment_date=date(2026, 9, 1))
        Payment.objects.create(workspace=self.workspace, amount=Decimal("200.00"), payment_method="upi", payment_date=date(2026, 9, 30))
        Payment.objects.create(workspace=self.workspace, amount=Decimal("900.00"), payment_method="bank", payment_date=date(2026, 10, 1))
        post_ledger_event(
            self.owner, self.workspace, event_type="refund_succeeded", event_key="p012c-refund-in",
            occurred_at=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc), amount=Decimal("50.00"), metadata={},
        )
        post_ledger_event(
            self.owner, self.workspace, event_type="refund_succeeded", event_key="p012c-refund-out",
            occurred_at=datetime(2026, 10, 1, 0, 1, tzinfo=timezone.utc), amount=Decimal("90.00"), metadata={},
        )
        report = collection_period_report(workspace=self.workspace, start=date(2026, 9, 1), end=date(2026, 9, 30))
        self.assertEqual(report["payments_recorded"], Decimal("300.00"))
        self.assertEqual(report["refunds_succeeded"], Decimal("50.00"))
        self.assertEqual(report["net_collections"], Decimal("250.00"))

    def test_collection_period_excludes_failed_refund(self):
        post_ledger_event(
            self.owner, self.workspace, event_type="refund_failed", event_key="p012c-refund-failed",
            occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc), amount=Decimal("75.00"), metadata={},
        )
        report = collection_period_report(workspace=self.workspace, start=date(2026, 9, 1), end=date(2026, 9, 30))
        self.assertEqual(report["refunds_succeeded"], Decimal("0.00"))
        self.assertEqual(report["net_collections"], Decimal("0.00"))

    def test_collection_period_is_workspace_scoped(self):
        Payment.objects.create(workspace=self.other_workspace, amount=Decimal("500.00"), payment_method="cash", payment_date=date(2026, 9, 10))
        post_ledger_event(
            self.other_owner, self.other_workspace, event_type="refund_succeeded", event_key="p012c-other-refund",
            occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc), amount=Decimal("100.00"), metadata={},
        )
        report = collection_period_report(workspace=self.workspace, start=date(2026, 9, 1), end=date(2026, 9, 30))
        self.assertEqual(report["payments_recorded"], Decimal("0.00"))
        self.assertEqual(report["refunds_succeeded"], Decimal("0.00"))

    def test_period_rejects_reversed_range_and_aging_rejects_invalid_date(self):
        with self.assertRaisesMessage(ValidationError, "Start date cannot be after end date"):
            collection_period_report(workspace=self.workspace, start=date(2026, 10, 1), end=date(2026, 9, 1))
        with self.assertRaisesMessage(ValidationError, "Invalid as_of date"):
            aging_report(workspace=self.workspace, as_of="2026-09-30")

    def test_period_and_aging_are_read_only(self):
        invoice = self.invoice(due_date=date(2026, 9, 1))
        payment = Payment.objects.create(workspace=self.workspace, amount=Decimal("25.00"), payment_method="cash", payment_date=date(2026, 9, 10))
        before = (invoice.paid_amount, invoice.status, invoice.total_amount, Payment.objects.count())
        collection_period_report(workspace=self.workspace, start=date(2026, 9, 1), end=date(2026, 9, 30))
        aging_report(workspace=self.workspace, as_of=self.as_of)
        invoice.refresh_from_db()
        after = (invoice.paid_amount, invoice.status, invoice.total_amount, Payment.objects.count())
        self.assertEqual(before, after)
        self.assertEqual(payment.amount, Decimal("25.00"))
