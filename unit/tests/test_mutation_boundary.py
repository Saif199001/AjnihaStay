from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.services import create_user_account
from properties.services import create_property
from django.utils.datastructures import MultiValueDict

from workspaces.models import Membership
from workspaces.services import add_member, deactivate_member
from unit.models import SubUnit, Unit
from unit.services import create_subunit, create_unit


class UnitMutationBoundaryTests(TestCase):
    def setUp(self):
        self.user = create_user_account(
            "unit-boundary@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Boundary Workspace",
        )
        self.workspace = self.user.owned_workspaces.get()

        self.property = create_property(
            self.user,
            self.workspace,
            {
                "owner": self.user,
                "name": "Unit Boundary Property",
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
        self.unit = create_unit(
            self.user,
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
        self.subunit = create_subunit(
            self.user,
            self.workspace,
            {
                "unit": self.unit,
                "subunit_number": "101-A",
                "rent": Decimal("5000"),
            },
        )

    def test_unit_direct_save_is_blocked(self):
        self.unit.description = "Changed"
        with self.assertRaises(PermissionDenied):
            self.unit.save()

    def test_unit_queryset_update_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            Unit.objects.filter(pk=self.unit.pk).update(description="Changed")

    def test_unit_queryset_bulk_update_is_blocked(self):
        self.unit.description = "Changed"
        with self.assertRaises(PermissionDenied):
            Unit.objects.bulk_update([self.unit], ["description"])

    def test_unit_queryset_bulk_create_is_blocked(self):
        candidate = Unit(
            property=self.property,
            unit_type="room",
            unit_number="102",
            rent=Decimal("10000"),
            capacity=1,
        )
        with self.assertRaises(PermissionDenied):
            Unit.objects.bulk_create([candidate])

    def test_unit_instance_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.unit.delete()

    def test_unit_queryset_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            Unit.objects.filter(pk=self.unit.pk).delete()

    def test_subunit_direct_save_is_blocked(self):
        self.subunit.rent = Decimal("4000")
        with self.assertRaises(PermissionDenied):
            self.subunit.save()

    def test_subunit_queryset_update_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            SubUnit.objects.filter(pk=self.subunit.pk).update(rent=Decimal("4000"))

    def test_subunit_queryset_bulk_update_is_blocked(self):
        self.subunit.rent = Decimal("4000")
        with self.assertRaises(PermissionDenied):
            SubUnit.objects.bulk_update([self.subunit], ["rent"])

    def test_subunit_queryset_bulk_create_is_blocked(self):
        candidate = SubUnit(
            unit=self.unit,
            subunit_number="101-B",
            rent=Decimal("4000"),
        )
        with self.assertRaises(PermissionDenied):
            SubUnit.objects.bulk_create([candidate])

    def test_subunit_instance_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.subunit.delete()

    def test_subunit_queryset_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            SubUnit.objects.filter(pk=self.subunit.pk).delete()

    def test_canonical_unit_and_subunit_services_remain_allowed(self):
        unit = create_unit(
            self.user,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "102",
                "unit_type": "room",
                "rent": Decimal("8000"),
                "capacity": 1,
                "description": "",
            },
        )
        subunit = create_subunit(
            self.user,
            self.workspace,
            {
                "unit": unit,
                "subunit_number": "102-A",
                "rent": Decimal("8000"),
            },
        )
        self.assertEqual(unit.property_id, self.property.pk)
        self.assertEqual(subunit.unit_id, unit.pk)


class UnitServiceAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "unit-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Authorization Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()
        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Unit Authorization Property",
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

        self.manager = create_user_account(
            "unit-manager@example.com", "StrongPassword123!", "StrongPassword123!", "Manager Workspace"
        )
        self.admin = create_user_account(
            "unit-admin@example.com", "StrongPassword123!", "StrongPassword123!", "Admin Workspace"
        )
        self.viewer = create_user_account(
            "unit-viewer@example.com", "StrongPassword123!", "StrongPassword123!", "Viewer Workspace"
        )
        self.inactive_manager = create_user_account(
            "unit-inactive@example.com", "StrongPassword123!", "StrongPassword123!", "Inactive Workspace"
        )

        actor_membership = self.owner.workspace_memberships.get()
        add_member(self.workspace, actor_membership, self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, actor_membership, self.admin.email, Membership.ROLE_ADMIN)
        add_member(self.workspace, actor_membership, self.viewer.email, Membership.ROLE_VIEWER)
        add_member(self.workspace, actor_membership, self.inactive_manager.email, Membership.ROLE_MANAGER)

    def _unit_data(self, number="201"):
        return {
            "property": self.property,
            "unit_number": number,
            "unit_type": "room",
            "rent": Decimal("10000"),
            "capacity": 2,
            "description": "",
        }

    def _subunit_data(self, unit):
        return {
            "unit": unit,
            "subunit_number": "201-A",
            "rent": Decimal("5000"),
        }

    def test_owner_can_create_unit(self):
        unit = create_unit(self.owner, self.workspace, self._unit_data())
        self.assertEqual(unit.property_id, self.property.pk)

    def test_manager_can_create_unit(self):
        unit = create_unit(self.manager, self.workspace, self._unit_data("202"))
        self.assertEqual(unit.property_id, self.property.pk)

    def test_admin_can_create_unit(self):
        unit = create_unit(self.admin, self.workspace, self._unit_data("203"))
        self.assertEqual(unit.property_id, self.property.pk)

    def test_viewer_cannot_create_unit(self):
        with self.assertRaises(PermissionDenied):
            create_unit(self.viewer, self.workspace, self._unit_data("204"))

    def test_inactive_member_cannot_create_unit(self):
        deactivate_member(self.workspace, self.owner.workspace_memberships.get(), self.inactive_manager.pk)
        with self.assertRaises(PermissionDenied):
            create_unit(self.inactive_manager, self.workspace, self._unit_data("205"))

    def test_non_member_cannot_create_unit(self):
        outsider = create_user_account(
            "unit-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Outsider Workspace",
        )
        with self.assertRaises(PermissionDenied):
            create_unit(outsider, self.workspace, self._unit_data("206"))

    def test_none_actor_cannot_create_unit(self):
        with self.assertRaises(PermissionDenied):
            create_unit(None, self.workspace, self._unit_data("207"))

    def test_owner_can_create_subunit(self):
        unit = create_unit(self.owner, self.workspace, self._unit_data("208"))
        subunit = create_subunit(self.owner, self.workspace, self._subunit_data(unit))
        self.assertEqual(subunit.unit_id, unit.pk)

    def test_manager_can_create_subunit(self):
        unit = create_unit(self.owner, self.workspace, self._unit_data("209"))
        subunit = create_subunit(self.manager, self.workspace, self._subunit_data(unit))
        self.assertEqual(subunit.unit_id, unit.pk)

    def test_viewer_cannot_create_subunit(self):
        unit = create_unit(self.owner, self.workspace, self._unit_data("210"))
        with self.assertRaises(PermissionDenied):
            create_subunit(self.viewer, self.workspace, self._subunit_data(unit))

    def test_non_member_cannot_create_subunit(self):
        unit = create_unit(self.owner, self.workspace, self._unit_data("211"))
        outsider = create_user_account(
            "unit-outsider-subunit@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Outsider SubUnit Workspace",
        )
        with self.assertRaises(PermissionDenied):
            create_subunit(outsider, self.workspace, self._subunit_data(unit))


class UnitPropertyStructureTests(TestCase):
    def setUp(self):
        self.user = create_user_account(
            "unit-structure@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Structure Workspace",
        )
        self.workspace = self.user.owned_workspaces.get()

    def _create_property(self, property_type):
        return create_property(
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

    def _create_unit(self, property_obj, number):
        return create_unit(
            self.user,
            self.workspace,
            {
                "property": property_obj,
                "unit_number": number,
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 2,
                "description": "",
            },
        )

    def test_pg_allows_subunit(self):
        property_obj = self._create_property("pg")
        unit = self._create_unit(property_obj, "PG-101")
        subunit = create_subunit(
            self.user,
            self.workspace,
            {"unit": unit, "subunit_number": "PG-101-A", "rent": Decimal("5000")},
        )
        self.assertEqual(subunit.unit_id, unit.pk)

    def test_hostel_allows_subunit(self):
        property_obj = self._create_property("hostel")
        unit = self._create_unit(property_obj, "HOSTEL-101")
        subunit = create_subunit(
            self.user,
            self.workspace,
            {"unit": unit, "subunit_number": "HOSTEL-101-A", "rent": Decimal("5000")},
        )
        self.assertEqual(subunit.unit_id, unit.pk)

    def test_non_subunit_property_types_reject_subunit(self):
        for property_type in ("shop", "flat", "office", "building"):
            with self.subTest(property_type=property_type):
                property_obj = self._create_property(property_type)
                unit = self._create_unit(property_obj, f"{property_type}-101")
                with self.assertRaisesMessage(
                    ValidationError,
                    "SubUnit is not allowed for this property type",
                ):
                    create_subunit(
                        self.user,
                        self.workspace,
                        {
                            "unit": unit,
                            "subunit_number": f"{property_type}-101-A",
                            "rent": Decimal("5000"),
                        },
                    )
                self.assertFalse(SubUnit.objects.filter(unit=unit).exists())
