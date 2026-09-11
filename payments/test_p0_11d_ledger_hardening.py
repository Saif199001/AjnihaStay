from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.test import TestCase, skipUnlessDBFeature

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .ledger_models import FinancialLedgerEntry
from .ledger_service import post_ledger_event
from .models import Invoice, Payment


class LedgerHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ledger-hardening@example.com", "password")
        self.other_owner = User.objects.create_user("ledger-hardening-other@example.com", "password")
        self.workspace = Workspace.objects.create(name="Hardening", slug="ledger-hardening", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Hardening", slug="ledger-hardening-other", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Hardening Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="H-1", rent=Decimal("10000.00"))
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Hardening Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False,
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 9, 30),
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace, invoice=self.invoice, amount=Decimal("100.00"),
            payment_method="cash", payment_date=date(2026, 9, 30),
        )
        self.occurred_at = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    def post(self, **overrides):
        data = {
            "event_type": "invoice_created",
            "event_key": "hardening:invoice:1",
            "occurred_at": self.occurred_at,
            "amount": Decimal("100.00"),
            "invoice": self.invoice,
            "occupancy": self.occupancy,
        }
        data.update(overrides)
        return post_ledger_event(self.owner, self.workspace, **data)

    def test_created_at_is_immutable(self):
        entry = self.post()
        original = entry.created_at
        entry.created_at = original + timedelta(minutes=1)
        with self.assertRaisesMessage(ValidationError, "Financial ledger entries cannot be changed after creation"):
            entry.save()

    def test_invoice_and_occupancy_relationship_must_match(self):
        other_property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Other Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110002",
        )
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="H-2", rent=Decimal("9000.00"))
        other_tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Other Tenant",
            phone="8888888888", permanent_address="Delhi",
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant, unit=other_unit, allotted_by=self.owner, rent=Decimal("9000.00"),
            check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False,
        )
        with self.assertRaisesMessage(ValidationError, "Ledger invoice and occupancy must match"):
            self.post(occupancy=other_occupancy)

    def test_payment_and_invoice_relationship_must_match_when_payment_is_linked(self):
        other_invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 10, 1), billing_end=date(2026, 10, 31),
            rent_amount=Decimal("5000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 31),
        )
        with self.assertRaisesMessage(ValidationError, "Ledger payment and invoice must match"):
            self.post(payment=self.payment, invoice=other_invoice, occupancy=self.occupancy)

    def test_lifecycle_refresh_is_not_a_ledger_event(self):
        with self.assertRaisesMessage(ValidationError, "Unsupported ledger event type"):
            self.post(event_type="invoice_lifecycle_refreshed")

    @skipUnlessDBFeature("supports_transactions")
    def test_queryset_update_and_delete_are_blocked_on_postgresql(self):
        if connection.vendor != "postgresql":
            self.skipTest("Database trigger enforcement is PostgreSQL-specific")
        entry = self.post()
        with self.assertRaises(DatabaseError):
            FinancialLedgerEntry.objects.filter(pk=entry.pk).update(amount=Decimal("90.00"))
        with self.assertRaises(DatabaseError):
            FinancialLedgerEntry.objects.filter(pk=entry.pk).delete()
        self.assertTrue(FinancialLedgerEntry.objects.filter(pk=entry.pk).exists())
