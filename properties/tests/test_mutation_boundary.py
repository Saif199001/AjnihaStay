from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.models import Property
from properties.services import create_property
from workspaces.models import Membership
from workspaces.services import add_member


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


class PropertyServiceAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "property-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Property Authorization Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "property-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Manager Workspace",
        )
        self.admin = create_user_account(
            "property-admin@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Admin Workspace",
        )
        self.viewer = create_user_account(
            "property-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Viewer Workspace",
        )
        self.inactive_manager = create_user_account(
            "property-inactive@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Inactive Workspace",
        )

        add_member(self.workspace, self.owner.workspace_memberships.get(), self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, self.owner.workspace_memberships.get(), self.admin.email, Membership.ROLE_ADMIN)
        add_member(self.workspace, self.owner.workspace_memberships.get(), self.viewer.email, Membership.ROLE_VIEWER)
        add_member(self.workspace, self.owner.workspace_memberships.get(), self.inactive_manager.email, Membership.ROLE_MANAGER)

        self.inactive_membership = Membership.objects.get(
            workspace=self.workspace,
            user=self.inactive_manager,
        )
        with Membership._meta.model._default_manager.all().using("default"):
            pass

    def _data(self, name="Authorized Property"):
        return {
            "name": name,
            "property_type": "pg",
            "description": "",
            "address": "Test Address",
            "city": "Lucknow",
            "state": "Uttar Pradesh",
            "pincode": "226001",
            "amenities": [],
        }

    def test_owner_can_create_property(self):
        property_obj = create_property(self.owner, self.workspace, self._data(), MultiValueDict())
        self.assertEqual(property_obj.owner_id, self.owner.pk)

    def test_manager_can_create_property(self):
        property_obj = create_property(self.manager, self.workspace, self._data("Manager Property"), MultiValueDict())
        self.assertEqual(property_obj.owner_id, self.manager.pk)

    def test_admin_can_create_property(self):
        property_obj = create_property(self.admin, self.workspace, self._data("Admin Property"), MultiValueDict())
        self.assertEqual(property_obj.owner_id, self.admin.pk)

    def test_viewer_cannot_create_property(self):
        with self.assertRaises(PermissionDenied):
            create_property(self.viewer, self.workspace, self._data(), MultiValueDict())

    def test_inactive_member_cannot_create_property(self):
        from workspaces.models import _allow_membership_mutation

        with _allow_membership_mutation():
            self.inactive_membership.is_active = False
            self.inactive_membership.save(update_fields=["is_active", "updated_at"])

        with self.assertRaises(PermissionDenied):
            create_property(self.inactive_manager, self.workspace, self._data(), MultiValueDict())

    def test_non_member_cannot_create_property(self):
        outsider = create_user_account(
            "property-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Outsider Workspace",
        )
        with self.assertRaises(PermissionDenied):
            create_property(outsider, self.workspace, self._data(), MultiValueDict())

    def test_none_actor_cannot_create_property(self):
        with self.assertRaises(PermissionDenied):
            create_property(None, self.workspace, self._data(), MultiValueDict())
