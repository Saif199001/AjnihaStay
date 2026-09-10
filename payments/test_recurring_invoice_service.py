from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .billing_models import BillingSchedule
from .models import Invoice
from .recurring_invoice_service import generate_invoice_from_schedule


class RecurringInvoiceGenerationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("recurring-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("recurring-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Recurring Workspace", slug="recurring-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Recurring Workspace", slug="other-recurring-workspace", owner=self.other_owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

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
            unit_number="301",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Recurring Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy,
            frequency="monthly",
            amount=Decimal("1000.00"),
            next_run_date=date(2026, 9, 1),
        )

    def test_monthly_schedule_creates_invoice_charge_and_advances_schedule(self):
        invoice = generate_invoice_from_schedule(
            self.owner,
            self.workspace,
            self.schedule,
            billing_date=date(2026, 9, 1),
        )

        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 1)
        self.assertEqual(invoice.billing_start, date(2026, 9, 1))
        self.assertEqual(invoice.billing_end, date(2026, 9, 30))
        self.assertEqual(invoice.due_date, date(2026, 9, 30))
        self.assertEqual(invoice.rent_amount, Decimal("0.00"))
        self.assertEqual(invoice.charges_amount, Decimal("1000.00"))
        self.assertEqual(invoice.total_amount, Decimal("1000.00"))
        self.assertEqual(invoice.status, "pending")
        self.assertEqual(invoice.charges.count(), 1)

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 10, 1))

    def test_daily_schedule_uses_one_day_billing_period(self):
        self.schedule.frequency = "daily"
        self.schedule.next_run_date = date(2026, 9, 10)
        self.schedule.save()

        invoice = generate_invoice_from_schedule(
            self.owner,
            self.workspace,
            self.schedule,
            billing_date=date(2026, 9, 10),
        )

        self.assertEqual(invoice.billing_start, date(2026, 9, 10))
        self.assertEqual(invoice.billing_end, date(2026, 9, 10))
        self.assertEqual(invoice.charges_amount, Decimal("1000.00"))
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 11))

    def test_generation_requires_exact_next_run_date(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Billing date must match the billing schedule next run date",
        ):
            generate_invoice_from_schedule(
                self.owner,
                self.workspace,
                self.schedule,
                billing_date=date(2026, 9, 2),
            )

        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 1))

    def test_generation_is_workspace_scoped(self):
        with self.assertRaisesMessage(ValidationError, "Billing schedule not found"):
            generate_invoice_from_schedule(
                self.other_owner,
                self.other_workspace,
                self.schedule,
                billing_date=date(2026, 9, 1),
            )

        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 0)

    def test_generation_rejects_inactive_schedule(self):
        self.schedule.active = False
        self.schedule.save()

        with self.assertRaisesMessage(
            ValidationError,
            "Inactive billing schedule cannot generate an invoice",
        ):
            generate_invoice_from_schedule(
                self.owner,
                self.workspace,
                self.schedule,
                billing_date=date(2026, 9, 1),
            )

    @patch("payments.recurring_invoice_service.create_charge")
    def test_invoice_and_schedule_are_atomic_when_charge_creation_fails(self, create_charge_mock):
        create_charge_mock.side_effect = ValidationError("charge failed")

        with self.assertRaisesMessage(ValidationError, "charge failed"):
            generate_invoice_from_schedule(
                self.owner,
                self.workspace,
                self.schedule,
                billing_date=date(2026, 9, 1),
            )

        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 1))
