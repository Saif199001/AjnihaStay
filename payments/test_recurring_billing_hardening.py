from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .billing_models import BillingSchedule
from .recurring_billing_service import (
    generate_due_recurring_billing,
    generate_recurring_billing_occurrence,
)
from .models import Invoice
from .ledger_models import FinancialLedgerEntry


class RecurringBillingHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("rb-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Recurring Billing Workspace",
            slug="recurring-billing-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Recurring Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="RB-1",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Recurring Tenant",
            phone="8888888888",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
        )

    def make_schedule(self, **overrides):
        data = {
            "occupancy": self.occupancy,
            "frequency": "monthly",
            "amount": Decimal("10000.00"),
            "next_run_date": date(2026, 1, 31),
        }
        data.update(overrides)
        return BillingSchedule.objects.create(**data)

    def test_only_one_active_schedule_per_occupancy(self):
        self.make_schedule()
        with self.assertRaises(IntegrityError):
            self.make_schedule(next_run_date=date(2026, 2, 28))

    def test_monthly_anchor_does_not_drift_after_short_month(self):
        schedule = self.make_schedule(anchor_day=31)

        generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 1, 31)
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_date, date(2026, 2, 28))
        self.assertEqual(schedule.anchor_day, 31)

        generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 2, 28)
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_date, date(2026, 3, 31))
        self.assertEqual(schedule.anchor_day, 31)

    def test_occurrence_retry_is_idempotent_for_charge_and_invoice(self):
        schedule = self.make_schedule()
        first = generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 1, 31)
        )
        second = generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 1, 31)
        )

        self.assertEqual(first["charge"].id, second["charge"].id)
        self.assertEqual(first["invoice"].id, second["invoice"].id)
        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_recurring_invoice_uses_canonical_ledger_transition(self):
        schedule = self.make_schedule()
        result = generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 1, 31)
        )
        self.assertTrue(
            FinancialLedgerEntry.objects.filter(
                workspace=self.workspace,
                event_type="invoice_created",
                invoice=result["invoice"],
            ).exists()
        )

    def test_bounded_catch_up_processes_due_occurrences(self):
        schedule = self.make_schedule(next_run_date=date(2026, 1, 31), anchor_day=31)
        results = generate_due_recurring_billing(
            self.owner,
            self.workspace,
            schedule,
            as_of_date=date(2026, 4, 1),
            catch_up=True,
            max_occurrences=3,
        )
        self.assertEqual(len(results), 3)
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_date, date(2026, 4, 30))

    def test_checkout_deactivates_schedule_at_terminal_boundary(self):
        self.occupancy.check_out_date = date(2026, 2, 15)
        self.occupancy.save(update_fields=["check_out_date"])
        schedule = self.make_schedule(next_run_date=date(2026, 1, 31), anchor_day=31)

        generate_recurring_billing_occurrence(
            self.owner, self.workspace, schedule, date(2026, 1, 31)
        )
        schedule.refresh_from_db()
        self.assertFalse(schedule.active)
