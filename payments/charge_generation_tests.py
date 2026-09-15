from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Charge, Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .billing_models import BillingSchedule
from .charge_generation_service import generate_charge_from_schedule


class RecurringChargeGenerationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("recurring-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("recurring-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Recurring Workspace",
            slug="recurring-workspace",
            owner=self.owner,
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Recurring Workspace",
            slug="other-recurring-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(
            workspace=self.other_workspace,
            user=self.other_owner,
            role="owner",
        )

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Recurring Property",
            property_type="pg",
            address="Test Address",
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
            frequency="daily",
            amount=Decimal("500.00"),
            next_run_date=date(2026, 9, 10),
        )

    def test_generation_creates_charge_and_advances_next_run_date(self):
        charge = generate_charge_from_schedule(
            self.owner,
            self.workspace,
            self.schedule,
            date(2026, 9, 10),
        )

        self.assertEqual(charge.amount, Decimal("500.00"))
        self.assertEqual(charge.charge_date, date(2026, 9, 10))
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 11))
        self.assertEqual(Charge.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_retry_for_same_billing_period_cannot_duplicate_charge(self):
        generate_charge_from_schedule(
            self.owner,
            self.workspace,
            self.schedule,
            date(2026, 9, 10),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Charge date must match the billing schedule next run date",
        ):
            generate_charge_from_schedule(
                self.owner,
                self.workspace,
                self.schedule,
                date(2026, 9, 10),
            )

        self.assertEqual(Charge.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_generation_requires_the_deterministic_next_run_date(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Charge date must match the billing schedule next run date",
        ):
            generate_charge_from_schedule(
                self.owner,
                self.workspace,
                self.schedule,
                date(2026, 9, 11),
            )

        self.assertEqual(Charge.objects.filter(occupancy=self.occupancy).count(), 0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 10))

    def test_monthly_schedule_advances_to_next_calendar_month(self):
        self.schedule.frequency = "monthly"
        self.schedule.next_run_date = date(2026, 9, 30)
        self.schedule.save(update_fields=["frequency", "next_run_date", "updated_at"])

        generate_charge_from_schedule(
            self.owner,
            self.workspace,
            self.schedule,
            date(2026, 9, 30),
        )

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 10, 30))

    def test_generation_is_workspace_scoped(self):
        with self.assertRaisesMessage(ValidationError, "Billing schedule not found"):
            generate_charge_from_schedule(
                self.other_owner,
                self.other_workspace,
                self.schedule,
                date(2026, 9, 10),
            )

        self.assertEqual(Charge.objects.filter(occupancy=self.occupancy).count(), 0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, date(2026, 9, 10))
