from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from workspaces.models import Membership, Workspace
from .models import Unit
from .services import create_unit, create_subunit, get_units
from django.core.exceptions import ValidationError


class UnitWorkspaceIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("unit-owner@example.com", password)
        self.other = User.objects.create_user("unit-other@example.com", password)
        self.workspace = Workspace.objects.create(
            name="Unit Workspace", slug="unit-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Unit Workspace", slug="other-unit-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Unit Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        self.other_property = Property.objects.create(
            owner=self.other, workspace=self.other_workspace, name="Other Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110002",
        )
        self.unit = Unit.objects.create(
            property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000.00")
        )
        self.other_unit = Unit.objects.create(
            property=self.other_property, unit_type="room", unit_number="201", rent=Decimal("9000.00")
        )

    def test_unit_list_is_workspace_scoped(self):
        units = get_units(self.workspace)
        self.assertEqual(list(units.values_list("id", flat=True)), [self.unit.id])
        self.assertEqual(get_units(self.other_workspace).count(), 1)
        self.assertNotEqual(get_units(self.other_workspace).first().id, self.unit.id)

    def test_property_filter_cannot_escape_workspace(self):
        units = get_units(self.workspace, self.other_property.id)
        self.assertEqual(units.count(), 0)

    def test_create_unit_rejects_cross_workspace_property(self):
        with self.assertRaises(ValidationError):
            create_unit(self.workspace, {
                "property": self.other_property.id,
                "unit_number": "999",
                "unit_type": "room",
                "rent": "5000.00",
                "capacity": 1,
            })

    def test_create_subunit_rejects_cross_workspace_unit(self):
        with self.assertRaises(ValidationError):
            create_subunit(self.workspace, {
                "unit": self.other_unit.id,
                "subunit_number": "A",
                "rent": "4000.00",
            })

    def test_unit_api_list_is_workspace_scoped(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(
            "/api/units/",
            HTTP_X_WORKSPACE_ID=str(self.other_workspace.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [self.other_unit.id])

    def test_unit_api_create_rejects_cross_workspace_property(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            "/api/units/create/",
            {
                "property": self.other_property.id,
                "unit_number": "999",
                "unit_type": "room",
                "rent": "5000.00",
                "capacity": 1,
            },
            format="json",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(response.status_code, 400)
