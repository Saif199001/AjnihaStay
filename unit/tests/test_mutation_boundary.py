from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.services import create_user_account
from properties.services import create_property
from django.utils.datastructures import MultiValueDict
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
            self.workspace,
            {
                "unit": unit,
                "subunit_number": "102-A",
                "rent": Decimal("8000"),
            },
        )
        self.assertEqual(unit.property_id, self.property.pk)
        self.assertEqual(subunit.unit_id, unit.pk)
