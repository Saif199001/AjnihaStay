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


class BillingScheduleModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("recurring-owner@example.com", "StrongPass123!")
        self.other = User.objects.create_user("recurring-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Recurring Workspace", slug="recurring-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Recurring Workspace", slug="other-recurring-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Recurring Property",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="401", rent=Decimal("10000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Recurring Tenant",
            phone="7777777777", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )

    def test_valid_schedule_persists_without_financial_side_effects(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy,
            frequency="monthly",
            amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        self.assertEqual(schedule.amount, Decimal("10000.00"))
        self.assertEqual(self.occupancy.invoices.count(), 0)
        self.assertEqual(self.occupancy.charges.count(), 0)

    def test_non_positive_amount_rejected(self):
        with self.assertRaises(ValidationError):
            BillingSchedule.objects.create(
                occupancy=self.occupancy,
                frequency="monthly",
                amount=Decimal("0.00"),
                next_run_date=date(2026, 10, 1),
            )

    def test_next_run_before_check_in_rejected(self):
        with self.assertRaises(ValidationError):
            BillingSchedule.objects.create(
                occupancy=self.occupancy,
                frequency="monthly",
                amount=Decimal("10000.00"),
                next_run_date=date(2026, 8, 31),
            )

    def test_inactive_occupancy_cannot_have_active_schedule(self):
        self.occupancy.is_active = False
        self.occupancy.save()
        with self.assertRaises(ValidationError):
            BillingSchedule.objects.create(
                occupancy=self.occupancy,
                frequency="monthly",
                amount=Decimal("10000.00"),
                next_run_date=date(2026, 10, 1),
                active=True,
            )

    def test_cross_workspace_queryset_returns_no_schedule(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy,
            frequency="monthly",
            amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        self.assertTrue(
            BillingSchedule.objects.filter(
                id=schedule.id,
                occupancy__tenant__workspace=self.other_workspace,
            ).count() == 0
        )
