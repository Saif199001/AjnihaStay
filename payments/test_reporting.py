from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .ledger_models import FinancialLedgerEntry
from .ledger_service import post_ledger_event
from .models import Invoice, Payment
from .reporting import (
    invoice_financial_report,
    workspace_collection_summary,
    workspace_ledger_activity,
)


class FinancialReportingRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("reporting-owner@example.com", "reporting-test-password")
        self.other_owner = User.objects.create_user("reporting-other@example.com", "reporting-test-password")
        self.workspace = Workspace.objects.create(
            name="Reporting Workspace", slug="reporting-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Reporting Workspace", slug="other-reporting-workspace", owner=self.other_owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Reporting Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="601",
            rent=Decimal("12000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Reporting Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("12000.00"),
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
            rent_amount=Decimal("12000.00"),
            charges_amount=Decimal("500.00"),
            due_date=date(2026, 9, 30),
        )
        self.occurred_at = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    def test_invoice_report_matches_canonical_position(self):
        report = invoice_financial_report(workspace=self.workspace, invoice_id=self.invoice.pk)
        self.assertEqual(report["gross_receivable"], Decimal("12500.00"))
        self.assertEqual(report["debit_adjustments"], Decimal("0.00"))
        self.assertEqual(report["reducing_adjustments"], Decimal("0.00"))
        self.assertEqual(report["late_fee_total"], Decimal("0.00"))
        self.assertEqual(report["adjusted_receivable"], Decimal("12500.00"))
        self.assertEqual(report["settlement"], Decimal("0.00"))
        self.assertEqual(report["outstanding"], Decimal("12500.00"))

    def test_invoice_report_is_workspace_scoped(self):
        with self.assertRaisesMessage(ValidationError, "Invoice not found in workspace."):
            invoice_financial_report(workspace=self.other_workspace, invoice_id=self.invoice.pk)

    def test_reporting_does_not_mutate_invoice(self):
        before = (self.invoice.paid_amount, self.invoice.status, self.invoice.total_amount)
        invoice_financial_report(workspace=self.workspace, invoice_id=self.invoice.pk)
        self.invoice.refresh_from_db()
        after = (self.invoice.paid_amount, self.invoice.status, self.invoice.total_amount)
        self.assertEqual(before, after)

    def test_collection_summary_counts_recorded_cash_and_successful_refunds(self):
        Payment.objects.create(
            workspace=self.workspace, amount=Decimal("7000.00"), payment_method="upi", payment_date=date(2026, 9, 10)
        )
        Payment.objects.create(
            workspace=self.workspace, amount=Decimal("3000.00"), payment_method="cash", payment_date=date(2026, 9, 15)
        )
        post_ledger_event(
            self.owner, self.workspace, event_type="refund_succeeded", event_key="refund:reporting:success",
            occurred_at=self.occurred_at, amount=Decimal("1000.00"), payment=None, metadata={"test": True}
        )
        post_ledger_event(
            self.owner, self.workspace, event_type="refund_failed", event_key="refund:reporting:failed",
            occurred_at=self.occurred_at, amount=Decimal("500.00"), metadata={"test": True}
        )
        summary = workspace_collection_summary(workspace=self.workspace)
        self.assertEqual(summary["payments_recorded"], Decimal("10000.00"))
        self.assertEqual(summary["refunds_succeeded"], Decimal("1000.00"))
        self.assertEqual(summary["net_collections"], Decimal("9000.00"))

    def test_collection_summary_is_workspace_scoped(self):
        Payment.objects.create(
            workspace=self.other_workspace, amount=Decimal("9000.00"), payment_method="bank", payment_date=date(2026, 9, 12)
        )
        summary = workspace_collection_summary(workspace=self.workspace)
        self.assertEqual(summary["payments_recorded"], Decimal("0.00"))
        self.assertEqual(summary["refunds_succeeded"], Decimal("0.00"))
        self.assertEqual(summary["net_collections"], Decimal("0.00"))

    def test_ledger_activity_is_workspace_scoped_and_period_filtered(self):
        for key, occurred_at, amount, workspace, user in [
            ("ledger:reporting:inside", datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), "12000.00", self.workspace, self.owner),
            ("ledger:reporting:outside", datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc), "500.00", self.workspace, self.owner),
            ("ledger:reporting:other", datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), "999.00", self.other_workspace, self.other_owner),
        ]:
            post_ledger_event(
                user, workspace, event_type="invoice_created", event_key=key,
                occurred_at=occurred_at, amount=Decimal(amount),
                invoice=self.invoice if workspace == self.workspace else None,
                occupancy=self.occupancy if workspace == self.workspace else None,
            )
        entries = workspace_ledger_activity(
            workspace=self.workspace,
            start=datetime(2026, 9, 1, tzinfo=timezone.utc),
            end=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(list(entries.values_list("event_key", flat=True)), ["ledger:reporting:inside"])

    def test_ledger_activity_is_read_only(self):
        entry = post_ledger_event(
            self.owner, self.workspace, event_type="invoice_created", event_key="ledger:reporting:readonly",
            occurred_at=self.occurred_at, amount=Decimal("12000.00"), invoice=self.invoice, occupancy=self.occupancy,
        )
        before = FinancialLedgerEntry.objects.get(pk=entry.pk).amount
        list(workspace_ledger_activity(workspace=self.workspace))
        after = FinancialLedgerEntry.objects.get(pk=entry.pk).amount
        self.assertEqual(before, after)
