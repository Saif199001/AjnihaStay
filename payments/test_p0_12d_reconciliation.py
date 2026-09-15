from datetime import date, datetime, timezone
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .ledger_models import FinancialLedgerEntry
from .ledger_service import post_ledger_event
from .models import Invoice
from .reconciliation import ledger_reconciliation_report


class LedgerReconciliationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("recon-owner@example.com", "recon-password")
        self.other_owner = User.objects.create_user("recon-other@example.com", "recon-password")
        self.workspace = Workspace.objects.create(name="Recon Workspace", slug="recon-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Recon Workspace", slug="other-recon-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        property_obj = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Recon Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="501", rent=Decimal("10000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Recon Tenant", phone="9999999999", permanent_address="Delhi")
        self.occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30), next_due_date=date(2026, 10, 1), security_deposit=Decimal("5000.00"), deposit_paid=True)
        self.invoice = Invoice.objects.create(occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30), rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 9, 30))
        self.occurred_at = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    def add_invoice_event(self, amount=Decimal("10000.00"), occupancy=None):
        return post_ledger_event(self.owner, self.workspace, event_type="invoice_created", event_key=f"invoice:{self.invoice.pk}:created", occurred_at=self.occurred_at, amount=amount, invoice=self.invoice, occupancy=occupancy or self.occupancy)

    def test_clean_workspace_reconciles(self):
        self.add_invoice_event()
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertTrue(report["ok"])
        self.assertEqual(report["finding_count"], 0)

    def test_missing_event_is_reported(self):
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "missing_event")
        self.assertEqual(report["findings"][0]["event_key"], f"invoice:{self.invoice.pk}:created")

    def test_amount_mismatch_is_reported(self):
        self.add_invoice_event(amount=Decimal("9000.00"))
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertTrue(any(item["kind"] == "amount_mismatch" for item in report["findings"]))

    def test_relationship_mismatch_is_reported(self):
        other_property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Recon Property 2", property_type="pg", address="Delhi 2", city="Delhi", state="Delhi", pincode="110002")
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="502", rent=Decimal("10000.00"))
        other_tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Other Tenant", phone="8888888888", permanent_address="Delhi")
        other_occupancy = Occupancy.objects.create(tenant=other_tenant, unit=other_unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30), next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False)
        FinancialLedgerEntry.objects.bulk_create([FinancialLedgerEntry(workspace=self.workspace, event_type="invoice_created", event_key=f"invoice:{self.invoice.pk}:created", occurred_at=self.occurred_at, amount=self.invoice.total_amount, invoice=self.invoice, occupancy=other_occupancy)])
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertTrue(any(item["kind"] == "relationship_mismatch" for item in report["findings"]))

    def test_unexpected_event_type_is_reported(self):
        FinancialLedgerEntry.objects.bulk_create([FinancialLedgerEntry(workspace=self.workspace, event_type="payment_recorded", event_key=f"invoice:{self.invoice.pk}:created", occurred_at=self.occurred_at, amount=self.invoice.total_amount, invoice=self.invoice, occupancy=self.occupancy)])
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertTrue(any(item["kind"] == "unexpected_event" for item in report["findings"]))

    def test_orphan_event_is_reported(self):
        FinancialLedgerEntry.objects.create(workspace=self.workspace, event_type="invoice_created", event_key="invoice:999999:created", occurred_at=self.occurred_at, amount=Decimal("100.00"))
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertTrue(any(item["kind"] == "orphan_event" for item in report["findings"]))

    def test_workspace_isolation(self):
        other_property = Property.objects.create(owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg", address="Lucknow", city="Lucknow", state="UP", pincode="226001")
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="601", rent=Decimal("8000.00"))
        other_tenant = Tenant.objects.create(owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant", phone="7777777777", permanent_address="Lucknow")
        other_occupancy = Occupancy.objects.create(tenant=other_tenant, unit=other_unit, allotted_by=self.other_owner, rent=Decimal("8000.00"), check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30), next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False)
        other_invoice = Invoice.objects.create(occupancy=other_occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30), rent_amount=Decimal("8000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 9, 30))
        post_ledger_event(self.other_owner, self.other_workspace, event_type="invoice_created", event_key=f"invoice:{other_invoice.pk}:created", occurred_at=self.occurred_at, amount=other_invoice.total_amount, invoice=other_invoice, occupancy=other_occupancy)
        report = ledger_reconciliation_report(workspace=self.workspace)
        self.assertFalse(any(item["event_key"] == f"invoice:{other_invoice.pk}:created" for item in report["findings"]))
        self.assertEqual(report["workspace_id"], self.workspace.pk)

    def test_reconciliation_is_read_only(self):
        self.add_invoice_event()
        before_invoice = Invoice.objects.get(pk=self.invoice.pk).total_amount
        before_count = FinancialLedgerEntry.objects.count()
        ledger_reconciliation_report(workspace=self.workspace)
        self.assertEqual(Invoice.objects.get(pk=self.invoice.pk).total_amount, before_invoice)
        self.assertEqual(FinancialLedgerEntry.objects.count(), before_count)
