from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.models import Property
from properties.services import create_property


class PropertyMutationBoundaryTests(TestCase):
    def setUp(self):
        self.user = create_user_account(
            "property-boundary@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Property Boundary Workspace",
        )
        self.workspace = self.user.owned_workspaces.get()

        self.property = create_property(
            self.user,
            self.workspace,
            {
                "name": "Boundary Property",
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

    def test_direct_save_is_blocked(self):
        self.property.name = "Changed"
        with self.assertRaises(PermissionDenied):
            self.property.save()

    def test_queryset_update_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            Property.objects.filter(pk=self.property.pk).update(name="Changed")

    def test_queryset_bulk_update_is_blocked(self):
        self.property.name = "Changed"
        with self.assertRaises(PermissionDenied):
            Property.objects.bulk_update([self.property], ["name"])

    def test_queryset_bulk_create_is_blocked(self):
        candidate = Property(
            owner=self.user,
            workspace=self.workspace,
            name="Bulk Property",
            property_type="pg",
            has_subunits=True,
            address="Test Address",
            city="Lucknow",
            state="Uttar Pradesh",
            pincode="226001",
        )
        with self.assertRaises(PermissionDenied):
            Property.objects.bulk_create([candidate])

    def test_instance_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.property.delete()

    def test_queryset_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            Property.objects.filter(pk=self.property.pk).delete()

    def test_canonical_property_service_remains_allowed(self):
        created = create_property(
            self.user,
            self.workspace,
            {
                "name": "Second Property",
                "property_type": "hostel",
                "description": "",
                "address": "Second Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226002",
                "amenities": [],
            },
            MultiValueDict(),
        )
        self.assertEqual(created.workspace_id, self.workspace.pk)
        self.assertEqual(created.owner_id, self.user.pk)
