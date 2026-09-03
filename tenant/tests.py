from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace
from .models import Occupancy, Tenant
from .services import create_occupancy


class OccupancySecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Owner Workspace", slug="owner-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Test Property", property_type="pg",
            address="Test Address", city="Delhi", state="Delhi", pincode="110001",
        )
        self.other_property = Property.objects.create(
            owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg",
            address="Other Address", city="Delhi", state="Delhi", pincode="110002",
        )
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000.00"))
        self.other_unit = Unit.objects.create(property=self.other_property, unit_type="room", unit_number="201", rent=Decimal("9000.00"))
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Owner Tenant",
            phone="9999999999", permanent_address="Delhi",
        )

    def occupancy_data(self, unit_id):
        return {
            "tenant": self.tenant.id,
            "unit": unit_id,
            "rent": Decimal("10000.00"),
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": date(2026, 9, 1),
            "next_due_date": date(2026, 10, 1),
        }

    def test_cross_workspace_unit_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.other_unit.id))

    def test_cross_workspace_subunit_is_rejected(self):
        subunit = SubUnit.objects.create(unit=self.other_unit, subunit_number="A", rent=Decimal("5000.00"))
        data = self.occupancy_data(self.other_unit.id)
        data["subunit"] = subunit.id
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

    def test_overlapping_active_occupancy_is_rejected(self):
        Occupancy.objects.create(
            tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.unit.id))
