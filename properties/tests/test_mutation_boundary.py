from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.models import Property, PropertyImage, _allow_property_mutation
from properties.serializers import PropertySerializer
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
                "owner": self.user,
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

    def _create_property_image(self):
        with _allow_property_mutation():
            return PropertyImage.objects.create(
                property=self.property,
                caption="Boundary Image",
                is_primary=False,
            )

    def test_property_image_direct_create_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            PropertyImage.objects.create(
                property=self.property,
                caption="Blocked Image",
            )

    def test_property_image_direct_save_is_blocked(self):
        image = self._create_property_image()
        image.caption = "Changed"
        with self.assertRaises(PermissionDenied):
            image.save()

    def test_property_image_queryset_update_is_blocked(self):
        image = self._create_property_image()
        with self.assertRaises(PermissionDenied):
            PropertyImage.objects.filter(pk=image.pk).update(caption="Changed")

    def test_property_image_queryset_bulk_update_is_blocked(self):
        image = self._create_property_image()
        image.caption = "Changed"
        with self.assertRaises(PermissionDenied):
            PropertyImage.objects.bulk_update([image], ["caption"])

    def test_property_image_queryset_bulk_create_is_blocked(self):
        candidate = PropertyImage(
            property=self.property,
            caption="Bulk Image",
        )
        with self.assertRaises(PermissionDenied):
            PropertyImage.objects.bulk_create([candidate])

    def test_property_image_instance_delete_is_blocked(self):
        image = self._create_property_image()
        with self.assertRaises(PermissionDenied):
            image.delete()

    def test_property_image_queryset_delete_is_blocked(self):
        image = self._create_property_image()
        with self.assertRaises(PermissionDenied):
            PropertyImage.objects.filter(pk=image.pk).delete()

    def test_property_image_canonical_mutation_remains_allowed(self):
        with _allow_property_mutation():
            image = PropertyImage.objects.create(
                property=self.property,
                caption="Allowed Image",
            )
            image.caption = "Updated Image"
            image.save()
        self.assertEqual(image.caption, "Updated Image")

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


    def test_property_type_derives_has_subunits(self):
        expected = {
            "pg": True,
            "hostel": True,
            "shop": False,
            "flat": False,
            "office": False,
            "building": False,
        }

        for property_type, has_subunits in expected.items():
            with self.subTest(property_type=property_type):
                property_obj = create_property(
                    self.user,
                    self.workspace,
                    {
                        "owner": self.user,
                        "name": f"{property_type} Property",
                        "property_type": property_type,
                        "description": "",
                        "address": "Test Address",
                        "city": "Lucknow",
                        "state": "Uttar Pradesh",
                        "pincode": "226001",
                        "amenities": [],
                    },
                    MultiValueDict(),
                )
                self.assertEqual(property_obj.has_subunits, has_subunits)

    def test_has_subunits_is_read_only_in_serializer(self):
        serializer = PropertySerializer()
        self.assertTrue(serializer.fields["has_subunits"].read_only)

    def test_model_rejects_inconsistent_property_structure(self):
        candidate = Property(
            owner=self.user,
            workspace=self.workspace,
            name="Invalid Structure",
            property_type="pg",
            has_subunits=False,
            address="Test Address",
            city="Lucknow",
            state="Uttar Pradesh",
            pincode="226001",
        )
        with self.assertRaises(ValidationError):
            candidate.clean()

    def test_database_rejects_inconsistent_property_structure(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), _allow_property_mutation():
                Property.objects.bulk_create(
                    [
                        Property(
                            owner=self.user,
                            workspace=self.workspace,
                            name="Invalid DB Structure",
                            property_type="pg",
                            has_subunits=False,
                            address="Test Address",
                            city="Lucknow",
                            state="Uttar Pradesh",
                            pincode="226001",
                        )
                    ]
                )

    def test_canonical_property_service_remains_allowed(self):
        created = create_property(
            self.user,
            self.workspace,
            {
                "owner": self.user,
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

    def _data(self, name="Authorized Property", owner=None):
        return {
            "owner": owner or self.owner,
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
        property_obj = create_property(
            self.owner,
            self.workspace,
            self._data(owner=self.owner),
            MultiValueDict(),
        )
        self.assertEqual(property_obj.owner_id, self.owner.pk)

    def test_manager_can_create_property(self):
        property_obj = create_property(
            self.manager,
            self.workspace,
            self._data("Manager Property", owner=self.owner),
            MultiValueDict(),
        )
        self.assertEqual(property_obj.owner_id, self.owner.pk)

    def test_admin_can_create_property(self):
        property_obj = create_property(
            self.admin,
            self.workspace,
            self._data("Admin Property", owner=self.manager),
            MultiValueDict(),
        )
        self.assertEqual(property_obj.owner_id, self.manager.pk)

    def test_viewer_cannot_create_property(self):
        with self.assertRaises(PermissionDenied):
            create_property(
                self.viewer,
                self.workspace,
                self._data(owner=self.owner),
                MultiValueDict(),
            )

    def test_inactive_member_cannot_create_property(self):
        from workspaces.services import deactivate_member

        deactivate_member(
            self.workspace,
            self.owner.workspace_memberships.get(),
            self.inactive_manager.pk,
        )

        with self.assertRaises(PermissionDenied):
            create_property(
                self.inactive_manager,
                self.workspace,
                self._data(owner=self.owner),
                MultiValueDict(),
            )

    def test_non_member_cannot_create_property(self):
        outsider = create_user_account(
            "property-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Outsider Workspace",
        )
        with self.assertRaises(PermissionDenied):
            create_property(
                outsider,
                self.workspace,
                self._data(owner=self.owner),
                MultiValueDict(),
            )

    def test_none_actor_cannot_create_property(self):
        with self.assertRaises(PermissionDenied):
            create_property(
                None,
                self.workspace,
                self._data(owner=self.owner),
                MultiValueDict(),
            )


class PropertyOwnershipAssignmentTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "property-assignment-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Property Assignment Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "property-assignment-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Manager Workspace",
        )
        self.viewer = create_user_account(
            "property-assignment-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Viewer Workspace",
        )
        self.outsider = create_user_account(
            "property-assignment-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Outsider Workspace",
        )
        self.inactive_owner = create_user_account(
            "property-assignment-inactive@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Inactive Workspace",
        )

        actor = self.owner.workspace_memberships.get()
        add_member(
            self.workspace,
            actor,
            self.manager.email,
            Membership.ROLE_MANAGER,
        )
        add_member(
            self.workspace,
            actor,
            self.viewer.email,
            Membership.ROLE_VIEWER,
        )
        add_member(
            self.workspace,
            actor,
            self.inactive_owner.email,
            Membership.ROLE_MANAGER,
        )

    def _data(self, owner):
        return {
            "owner": owner,
            "name": "Explicit Owner Property",
            "property_type": "pg",
            "description": "",
            "address": "Test Address",
            "city": "Lucknow",
            "state": "Uttar Pradesh",
            "pincode": "226001",
            "amenities": [],
        }

    def test_creator_does_not_become_owner_implicitly(self):
        property_obj = create_property(
            self.manager,
            self.workspace,
            self._data(self.owner),
            MultiValueDict(),
        )
        self.assertEqual(property_obj.owner_id, self.owner.pk)
        self.assertNotEqual(property_obj.owner_id, self.manager.pk)

    def test_manager_can_assign_property_to_another_active_workspace_member(self):
        property_obj = create_property(
            self.manager,
            self.workspace,
            self._data(self.owner),
            MultiValueDict(),
        )
        self.assertEqual(property_obj.owner_id, self.owner.pk)

    def test_cross_workspace_property_owner_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_property(
                self.manager,
                self.workspace,
                self._data(self.outsider),
                MultiValueDict(),
            )

    def test_inactive_property_owner_is_rejected(self):
        from workspaces.services import deactivate_member

        deactivate_member(
            self.workspace,
            self.owner.workspace_memberships.get(),
            self.inactive_owner.pk,
        )

        with self.assertRaises(ValidationError):
            create_property(
                self.manager,
                self.workspace,
                self._data(self.inactive_owner),
                MultiValueDict(),
            )

    def test_missing_property_owner_is_rejected(self):
        data = self._data(self.owner)
        data.pop("owner")

        with self.assertRaises(ValidationError):
            create_property(
                self.manager,
                self.workspace,
                data,
                MultiValueDict(),
            )

    def test_viewer_cannot_assign_property_owner(self):
        with self.assertRaises(PermissionDenied):
            create_property(
                self.viewer,
                self.workspace,
                self._data(self.owner),
                MultiValueDict(),
            )
