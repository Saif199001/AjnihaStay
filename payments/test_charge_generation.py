from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .billing_models import BillingSchedule
from .charge_generation_service import generate_charge_from_schedule


class ChargeGenerationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("charge-generation-owner@example.com", "StrongPass123!")
        self.other = User.objects.create_user("charge-generation-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Charge Generation Workspace", slug="charge-generation-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Charge Generation Workspace", slug="other-charge-generation-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Charge Generation Property",
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
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Charge Generation Tenant",
            phone="7777777777",
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
            amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )

    def test_generates_charge_from_schedule_without_invoice_or_payment_side_effects(self):
        charge = generate_charge_from_schedule(
            self.owner, self.workspace, self.schedule, date(2026, 10, 1)
        )
        self.assertEqual(charge.occupancy_id, self.occupancy.id)
        self.assertEqual(charge.amount, Decimal("10000.00"))
        self.assertEqual(charge.charge_type, "custom")
        self.assertIn(f"schedule #{self.schedule.id}", charge.description)
        self.assertEqual(self.occupancy.invoices.count(), 0)
        self.assertEqual(self.occupancy.charges.count(), 1)

    def test_generation_does_not_advance_schedule(self):
        original_date = self.schedule.next_run_date
        generate_charge_from_schedule(
            self.owner, self.workspace, self.schedule, date(2026, 10, 1)
        )
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_run_date, original_date)

    def test_inactive_schedule_is_rejected(self):
        self.schedule.active = False
        self.schedule.save()
        with self.assertRaisesMessage(ValidationError, "Inactive billing schedule cannot generate a charge"):
            generate_charge_from_schedule(
                self.owner, self.workspace, self.schedule, date(2026, 10, 1)
            )

    def test_inactive_occupancy_is_rejected(self):
        self.occupancy.is_active = False
        self.occupancy.save()
        with self.assertRaisesMessage(ValidationError, "Inactive occupancy cannot generate a charge"):
            generate_charge_from_schedule(
                self.owner, self.workspace, self.schedule, date(2026, 10, 1)
            )

    def test_cross_workspace_schedule_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Billing schedule not found"):
            generate_charge_from_schedule(
                self.other, self.other_workspace, self.schedule, date(2026, 10, 1)
            )

    def test_invalid_charge_date_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Invalid charge date"):
            generate_charge_from_schedule(
                self.owner, self.workspace, self.schedule, "not-a-date"
            )

    def test_charge_before_check_in_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Charge date cannot be before occupancy check-in date"):
            generate_charge_from_schedule(
                self.owner, self.workspace, self.schedule, date(2026, 8, 31)
            )

    def test_charge_after_check_out_is_rejected(self):
        self.occupancy.check_out_date = date(2026, 9, 30)
        self.occupancy.save()
        with self.assertRaisesMessage(ValidationError, "Charge date cannot be after occupancy check-out date"):
            generate_charge_from_schedule(
                self.owner, self.workspace, self.schedule, date(2026, 10, 1)
            )

    def test_missing_charge_date_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Charge date is required"):
            generate_charge_from_schedule(self.owner, self.workspace, self.schedule)
