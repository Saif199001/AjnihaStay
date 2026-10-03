from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIClient

from accounts.services import create_user_account
from properties.services import create_property
from unit.services import create_subunit, create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class PropertyAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = create_user_account(
            "property-api-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Property API Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "property-api-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Manager Workspace",
        )
        self.viewer = create_user_account(
            "property-api-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Viewer Workspace",
        )
        actor = self.owner.workspace_memberships.get()
        add_member(self.workspace, actor, self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, actor, self.viewer.email, Membership.ROLE_VIEWER)

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "API Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        if workspace is not None:
            self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(workspace.pk)

    def test_list_requires_authentication(self):
        response = self.client.get("/api/properties/")
        self.assertEqual(response.status_code, 401)

    def test_viewer_can_list_workspace_properties(self):
        self.authenticate(self.viewer, self.workspace)
        response = self.client.get("/api/properties/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.data)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["id"], self.property.pk)

    def test_viewer_cannot_create_property(self):
        self.authenticate(self.viewer, self.workspace)
        response = self.client.post(
            "/api/properties/create/",
            {
                "owner": self.owner.pk,
                "name": "Blocked Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_property(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/properties/create/",
            {
                "owner": self.owner.pk,
                "name": "Created Through API",
                "property_type": "pg",
                "description": "",
                "address": "API Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226002",
                "amenities": ["wifi"],
                "has_subunits": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Property created successfully")
        self.assertEqual(response.data["data"]["name"], "Created Through API")
        self.assertTrue(response.data["data"]["has_subunits"])

    def test_invalid_property_payload_returns_serializer_400(self):
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/properties/create/",
            {
                "owner": self.owner.pk,
                "name": "   ",
                "property_type": "pg",
                "amenities": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_cross_workspace_property_header_is_rejected(self):
        other = create_user_account(
            "property-api-other@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Other Property API Workspace",
        )
        self.authenticate(self.owner, other.owned_workspaces.get())

        response = self.client.get("/api/properties/")

        self.assertEqual(response.status_code, 403)

    def test_cross_workspace_property_owner_is_rejected_by_service(self):
        other = create_user_account(
            "property-api-outsider@example.com",
            "StrongPassword123!",
            "Outsider Property API Workspace",
        )
        self.authenticate(self.manager, self.workspace)
        response = self.client.post(
            "/api/properties/create/",
            {
                "owner": other.pk,
                "name": "Cross Workspace Owner",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226003",
                "amenities": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Property owner must be an active workspace member")
