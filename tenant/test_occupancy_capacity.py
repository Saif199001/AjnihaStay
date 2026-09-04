from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace
from .models import Occupancy, Tenant
from .services import create_occupancy


class OccupancyCapacityAndDateTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("capacity-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Capacity Workspace", slug="capacity-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Capacity Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="101",
            rent=Decimal("10000.00"),
            capacity=2,
        )
        self.tenant1 = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Tenant One",
            phone="9999999001",
            permanent_address="Delhi",
        )
        self.tenant2 = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Tenant Two",
            phone="9999999002",
            permanent_address="Delhi",
        )
        self.tenant3 = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Tenant Three",
            phone="9999999003",
            permanent_address="Delhi",
        )

    def occupancy_data(self, tenant_id, check_in=date(2026, 9, 1), check_out=None):
        return {
            "tenant": tenant_id,
            "unit": self.unit.id,
            "rent": Decimal("10000.00"),
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": check_in,
            "check_out_date": check_out,
            "next_due_date": date(2026, 10, 1),
        }

    def test_unit_capacity_allows_multiple_overlapping_occupants(self):
        first = create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant1.id))
        second = create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant2.id))
        self.assertEqual(Occupancy.objects.filter(unit=self.unit, is_active=True).count(), 2)
        self.assertNotEqual(first.id, second.id)

    def test_unit_capacity_blocks_occupant_above_capacity(self):
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant1.id))
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant2.id))
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant3.id))

    def test_finished_occupancy_does_not_block_future_occupancy(self):
        data = self.occupancy_data(self.tenant1.id, check_out=date(2026, 9, 10))
        create_occupancy(self.owner, self.workspace, data)
        future = self.occupancy_data(self.tenant2.id, check_in=date(2026, 9, 11))
        create_occupancy(self.owner, self.workspace, future)
        self.assertEqual(Occupancy.objects.filter(unit=self.unit).count(), 2)

    def test_date_overlap_still_counts_against_capacity(self):
        create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(self.tenant1.id, check_in=date(2026, 9, 1), check_out=date(2026, 9, 10)),
        )
        create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(self.tenant2.id, check_in=date(2026, 9, 5), check_out=date(2026, 9, 15)),
        )
        with self.assertRaises(ValidationError):
            create_occupancy(
                self.owner,
                self.workspace,
                self.occupancy_data(self.tenant3.id, check_in=date(2026, 9, 10), check_out=date(2026, 9, 20)),
            )

    def test_inactive_occupancy_does_not_count_against_capacity(self):
        occupancy = Occupancy.objects.create(
            tenant=self.tenant1,
            unit=self.unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
            is_active=False,
        )
        self.assertFalse(occupancy.is_active)
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant2.id))
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant3.id))
        self.assertEqual(Occupancy.objects.filter(unit=self.unit, is_active=True).count(), 2)

    def test_inactive_unit_cannot_receive_occupancy(self):
        self.unit.is_active = False
        self.unit.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant1.id))

    def test_subunit_reuse_after_checkout_is_allowed(self):
        subunit = SubUnit.objects.create(unit=self.unit, subunit_number="A", rent=Decimal("5000.00"))
        first = self.occupancy_data(self.tenant1.id, check_out=date(2026, 9, 10))
        first["subunit"] = subunit.id
        create_occupancy(self.owner, self.workspace, first)
        second = self.occupancy_data(self.tenant2.id, check_in=date(2026, 9, 11))
        second["subunit"] = subunit.id
        create_occupancy(self.owner, self.workspace, second)
        self.assertEqual(Occupancy.objects.filter(subunit=subunit).count(), 2)

    def test_invalid_unit_capacity_is_rejected(self):
        with self.assertRaises(ValidationError):
            Unit.objects.create(
                property=self.property,
                unit_type="room",
                unit_number="102",
                rent=Decimal("10000.00"),
                capacity=0,
            )

    def test_invalid_unit_rent_is_rejected(self):
        with self.assertRaises(ValidationError):
            Unit.objects.create(
                property=self.property,
                unit_type="room",
                unit_number="103",
                rent=Decimal("-1.00"),
                capacity=1,
            )

    def test_database_constraint_blocks_invalid_capacity(self):
        with self.assertRaises(IntegrityError):
            Unit.objects.bulk_create([
                Unit(
                    property=self.property,
                    unit_type="room",
                    unit_number="104",
                    rent=Decimal("10000.00"),
                    capacity=0,
                )
            ])
