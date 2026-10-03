from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.services import create_user_account
from properties.services import create_property
from unit.services import create_subunit, create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class UnitAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = create_user_account(
            "unit-api-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit API Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "unit-api-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Manager Workspace",
        )
        self.viewer = create_user_account(
            "unit-api-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Viewer Workspace",
        )
        actor = self.owner.workspace_memberships.get()
        add_member(self.workspace, actor, self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, actor, self.viewer.email, Membership.ROLE_VIEWER)

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Unit API Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            {},
        )
        self.unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 2,
                "description": "",
            },
        )

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        if workspace is not None:
            self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(workspace.pk)

    def test_unit_list_requires_authentication(self):
        response = self.client.get("/api/units/")
        self.assertEqual(response.status_code, 401)

    def test_viewer_can_list_units(self):
        self.authenticate(self.viewer, self.workspace)
        response = self.client.get("/api/units/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.data)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["id"], self.unit.pk)

    def test_property_filter_returns_only_requested_workspace_units(self):
        other = create_user_account(
            "unit-api-other@example.com",
            "StrongPassword123!",
            "Unit Other Workspace",
        )
        other_workspace = other.owned_workspaces.get()
        other_property = create_property(
            other,
            other_workspace,
            {
                "owner": other,
                "name": "Other Property",
                "property_type": "pg",
                "description": "",
                "address": "Other Address",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110001",
                "amenities": [],
            },
            {},
        )
        self.authenticate(self.viewer, self.workspace)
        response = self.client.get(
            "/api/units/",
            {"property": other_property.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_manager_can_create_unit(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/units/create/",
            {
                "property": self.property.pk,
                "unit_number": "102",
                "unit_type": "room",
                "rent": "8000",
                "capacity": 2,
                "description": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Unit created")
        self.assertEqual(response.data["data"]["unit_number"], "102")

    def test_viewer_cannot_create_unit(self):
        self.authenticate(self.viewer, self.workspace)
        response = self.client.post(
            "/api/units/create/",
            {
                "property": self.property.pk,
                "unit_number": "103",
                "unit_type": "room",
                "rent": "8000",
                "capacity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_invalid_unit_rent_returns_serializer_400(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/units/create/",
            {
                "property": self.property.pk,
                "unit_number": "104",
                "unit_type": "room",
                "rent": "0",
                "capacity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rent", response.data)

    def test_cross_workspace_property_is_rejected(self):
        other = create_user_account(
            "unit-api-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Outsider Workspace",
        )
        other_property = create_property(
            other,
            other.owned_workspaces.get(),
            {
                "owner": other,
                "name": "Outsider Property",
                "property_type": "pg",
                "description": "",
                "address": "Other Address",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110002",
                "amenities": [],
            },
            {},
        )
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/units/create/",
            {
                "property": other_property.pk,
                "unit_number": "105",
                "unit_type": "room",
                "rent": "8000",
                "capacity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Property not found")

    def test_manager_can_create_subunit(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/subunits/create/",
            {
                "unit": self.unit.pk,
                "subunit_number": "101-A",
                "rent": "5000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "SubUnit created")
        self.assertEqual(response.data["data"]["subunit_number"], "101-A")

    def test_viewer_cannot_create_subunit(self):
        self.authenticate(self.viewer, self.workspace)
        response = self.client.post(
            "/api/subunits/create/",
            {
                "unit": self.unit.pk,
                "subunit_number": "101-B",
                "rent": "5000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_invalid_subunit_rent_returns_serializer_400(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/subunits/create/",
            {
                "unit": self.unit.pk,
                "subunit_number": "101-C",
                "rent": "0",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rent", response.data)

    def test_non_subunit_property_rejects_subunit_via_api(self):
        property_obj = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Shop API Property",
                "property_type": "shop",
                "description": "",
                "address": "Shop Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226004",
                "amenities": [],
            },
            {},
        )
        unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": property_obj,
                "unit_number": "SHOP-1",
                "unit_type": "shop",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/subunits/create/",
            {
                "unit": unit.pk,
                "subunit_number": "SHOP-1-A",
                "rent": "5000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "SubUnit is not allowed for this property type",
        )

    def test_cross_workspace_unit_is_rejected(self):
        other = create_user_account(
            "unit-api-cross@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Cross Workspace",
        )
        other_workspace = other.owned_workspaces.get()
        other_property = create_property(
            other,
            other_workspace,
            {
                "owner": other,
                "name": "Cross Property",
                "property_type": "pg",
                "description": "",
                "address": "Other Address",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110003",
                "amenities": [],
            },
            {},
        )
        other_unit = create_unit(
            other,
            other_workspace,
            {
                "property": other_property,
                "unit_number": "201",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/subunits/create/",
            {
                "unit": other_unit.pk,
                "subunit_number": "201-A",
                "rent": "5000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Unit not found")
