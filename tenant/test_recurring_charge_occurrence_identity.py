from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from payments.billing_models import BillingSchedule
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .models import Charge, Occupancy, Tenant


class RecurringChargeOccurrenceIdentityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("f4-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="F4 Workspace", slug="f4-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="F4 Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="F4-1",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="F4 Tenant",
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

    def test_same_schedule_and_date_cannot_create_two_recurring_occurrences(self):
        Charge.objects.create(
            occupancy=self.occupancy,
            billing_schedule=self.schedule,
            charge_type="custom",
            amount=Decimal("10000.00"),
            charge_date=date(2026, 10, 1),
        )
        with self.assertRaises(IntegrityError):
            Charge.objects.create(
                occupancy=self.occupancy,
                billing_schedule=self.schedule,
                charge_type="custom",
                amount=Decimal("10000.00"),
                charge_date=date(2026, 10, 1),
            )

    def test_same_schedule_can_have_multiple_distinct_occurrence_dates(self):
        Charge.objects.create(
            occupancy=self.occupancy,
            billing_schedule=self.schedule,
            charge_type="custom",
            amount=Decimal("10000.00"),
            charge_date=date(2026, 10, 1),
        )
        Charge.objects.create(
            occupancy=self.occupancy,
            billing_schedule=self.schedule,
            charge_type="custom",
            amount=Decimal("10000.00"),
            charge_date=date(2026, 11, 1),
        )
        self.assertEqual(Charge.objects.filter(billing_schedule=self.schedule).count(), 2)

    def test_schedule_must_belong_to_charge_occupancy(self):
        other_unit = Unit.objects.create(
            property=self.occupancy.unit.property,
            unit_type="room",
            unit_number="F4-2",
            rent=Decimal("10000.00"),
        )
        other_tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="F4 Other Tenant",
            phone="6666666666",
            permanent_address="Delhi",
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        with self.assertRaisesMessage(
            ValidationError, "Billing schedule must belong to the charge occupancy"
        ):
            Charge.objects.create(
                occupancy=other_occupancy,
                billing_schedule=self.schedule,
                charge_type="custom",
                amount=Decimal("10000.00"),
                charge_date=date(2026, 10, 1),
            )
