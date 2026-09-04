from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from workspaces.models import Membership, Workspace
from .models import Unit, SubUnit
from .serializers import UnitSerializer
from .services import create_unit, create_subunit, get_units


class UnitWorkspaceIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("unit-owner@example.com", password)
        self.other = User.objects.create_user("unit-other@example.com", password)
        self.workspace = Workspace.objects.create(name="Unit Workspace", slug="unit-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Unit Workspace", slug="other-unit-workspace", owner=self.other)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")
        self.property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Unit Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        self.other_property = Property.objects.create(owner=self.other, workspace=self.other_workspace, name="Other Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110002")
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000.00"))
        self.other_unit = Unit.objects.create(property=self.other_property, unit_type="room", unit_number="201", rent=Decimal("9000.00"))

    def test_unit_list_is_workspace_scoped(self):
        units = get_units(self.workspace)
        self.assertEqual(list(units.values_list("id", flat=True)), [self.unit.id])
        self.assertEqual(get_units(self.other_workspace).count(), 1)
        self.assertNotEqual(get_units(self.other_workspace).first().id, self.unit.id)

    def test_property_filter_cannot_escape_workspace(self):
        self.assertEqual(get_units(self.workspace, self.other_property.id).count(), 0)

    def test_get_units_rejects_malformed_property_id(self):
        with self.assertRaisesMessage(ValidationError, "Invalid property ID"):
            get_units(self.workspace, "not-a-number")

    def test_get_units_rejects_zero_property_id(self):
        with self.assertRaisesMessage(ValidationError, "Invalid property ID"):
            get_units(self.workspace, "0")

    def test_create_unit_rejects_cross_workspace_property(self):
        with self.assertRaises(ValidationError):
            create_unit(self.workspace, {"property": self.other_property.id, "unit_number": "999", "unit_type": "room", "rent": "5000.00", "capacity": 1})

    def test_create_subunit_rejects_cross_workspace_unit(self):
        with self.assertRaises(ValidationError):
            create_subunit(self.workspace, {"unit": self.other_unit.id, "subunit_number": "A", "rent": "4000.00"})

    def test_unit_serializer_accepts_property_id_and_returns_nested_property(self):
        serializer = UnitSerializer(instance=self.unit)
        self.assertEqual(serializer.data["property"]["id"], self.property.id)
        input_serializer = UnitSerializer(data={"property": self.property.id, "unit_number": "102", "unit_type": "room", "rent": "9000.00", "capacity": 1})
        self.assertTrue(input_serializer.is_valid(), input_serializer.errors)
        self.assertEqual(input_serializer.validated_data["property"], self.property)

    def test_unit_occupancy_read_semantics_ignore_subunit_occupancy(self):
        unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="102",
            rent=Decimal("10000.00"),
            capacity=2,
        )
        subunit = SubUnit.objects.create(
            unit=unit,
            subunit_number="A",
            rent=Decimal("5000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="SubUnit Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            subunit=subunit,
            allotted_by=self.owner,
            rent=Decimal("5000.00"),
            check_in_date=date(2026, 9, 1),
            check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1),
        )

        serializer = UnitSerializer(instance=unit)
        self.assertEqual(serializer.data["occupied_count"], 0)
        self.assertEqual(serializer.data["occupancy_status"], "Vacant")
        self.assertFalse(unit.is_occupied())
        self.assertTrue(subunit.is_occupied())

    def test_unit_occupancy_read_semantics_count_unit_level_occupancy(self):
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Unit Tenant",
            phone="9999999998",
            permanent_address="Delhi",
        )
        Occupancy.objects.create(
            tenant=tenant,
            unit=self.unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1),
        )

        serializer = UnitSerializer(instance=self.unit)
        self.assertEqual(serializer.data["occupied_count"], 1)
        self.assertEqual(serializer.data["occupancy_status"], "Full")
        self.assertTrue(self.unit.is_occupied())

    def test_unit_api_list_is_workspace_scoped(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get("/api/units/", HTTP_X_WORKSPACE_ID=str(self.other_workspace.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [self.other_unit.id])

    def test_unit_api_create_works_with_property_id(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post("/api/units/create/", {"property": self.property.id, "unit_number": "102", "unit_type": "room", "rent": "9000.00", "capacity": 1}, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 200)
        created = Unit.objects.get(property=self.property, unit_number="102")
        self.assertEqual(response.data["data"]["property"]["id"], self.property.id)
        self.assertEqual(created.property_id, self.property.id)

    def test_unit_api_create_rejects_cross_workspace_property(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post("/api/units/create/", {"property": self.other_property.id, "unit_number": "999", "unit_type": "room", "rent": "5000.00", "capacity": 1}, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 400)

    def test_unit_api_list_rejects_malformed_property_id(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/api/units/?property=not-a-number", HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid property ID")

    def test_unit_api_list_rejects_zero_property_id(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/api/units/?property=0", HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid property ID")
