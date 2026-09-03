from rest_framework.test import APIClient
from django.test import TestCase

from accounts.models import User
from workspaces.models import Membership, Workspace
from .models import Property
from .serializers import PropertySerializer


class PropertyWorkspaceIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("property-owner@example.com", password)
        self.other = User.objects.create_user("property-other@example.com", password)
        self.workspace = Workspace.objects.create(
            name="Owner Workspace", slug="property-owner-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Workspace", slug="property-other-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Owner Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )

    def test_serializer_cannot_assign_owner_or_workspace(self):
        serializer = PropertySerializer(data={
            "owner": self.other.id,
            "workspace": self.other_workspace.id,
            "name": "Injected Property",
            "property_type": "pg",
            "address": "Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110002",
            "amenities": [],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("owner", serializer.validated_data)
        self.assertNotIn("workspace", serializer.validated_data)

    def test_property_list_does_not_return_other_workspace(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(
            "/api/properties/",
            HTTP_X_WORKSPACE_ID=str(self.other_workspace.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_property_create_uses_selected_workspace_not_client_supplied_workspace(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            "/api/properties/create/",
            {
                "name": "New Property",
                "property_type": "pg",
                "address": "Delhi",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110003",
                "workspace": self.other_workspace.id,
                "owner": self.other.id,
                "amenities": [],
            },
            format="json",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(response.status_code, 200)
        created = Property.objects.get(name="New Property")
        self.assertEqual(created.workspace_id, self.workspace.id)
        self.assertEqual(created.owner_id, self.owner.id)
