from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.services import create_property
from unit.models import _allow_unit_mutation
from unit.services import create_subunit, create_unit


class UnitCapacityContractTests(TestCase):
    def setUp(self):
        self.user = create_user_account(
            "unit-capacity@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Unit Capacity Workspace",
        )
        self.workspace = self.user.owned_workspaces.get()
        self.property = create_property(
            self.user,
            self.workspace,
            {
                "owner": self.user,
                "name": "Unit Capacity Property",
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

    def _create_unit(self, number="101", capacity=2):
        return create_unit(
            self.user,
            self.workspace,
            {
                "property": self.property,
                "unit_number": number,
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": capacity,
                "description": "",
            },
        )

    def _create_subunit(self, unit, number, rent="4000"):
        return create_subunit(
            self.user,
            self.workspace,
            {
                "unit": unit,
                "subunit_number": number,
                "rent": Decimal(rent),
            },
        )

    def test_subunit_based_unit_cannot_reduce_capacity_below_active_subunits(self):
        unit = self._create_unit(capacity=2)
        self._create_subunit(unit, "101-A")
        self._create_subunit(unit, "101-B")

        unit.capacity = 1

        with self.assertRaisesMessage(
            ValidationError,
            "Unit capacity cannot be reduced below active SubUnit count",
        ):
            with _allow_unit_mutation():
                unit.save()

        unit.refresh_from_db()
        self.assertEqual(unit.capacity, 2)
        self.assertEqual(unit.subunits.filter(is_active=True).count(), 2)

    def test_subunit_based_unit_can_keep_capacity_equal_to_active_subunits(self):
        unit = self._create_unit(capacity=2)
        self._create_subunit(unit, "102-A")
        self._create_subunit(unit, "102-B")

        unit.capacity = 2
        with _allow_unit_mutation():
            unit.save()

        unit.refresh_from_db()
        self.assertEqual(unit.capacity, 2)

    def test_subunit_based_unit_can_increase_capacity(self):
        unit = self._create_unit(capacity=2)
        self._create_subunit(unit, "103-A")
        self._create_subunit(unit, "103-B")

        unit.capacity = 3
        with _allow_unit_mutation():
            unit.save()

        unit.refresh_from_db()
        self.assertEqual(unit.capacity, 3)

    def test_inactive_subunits_do_not_consume_capacity(self):
        unit = self._create_unit(capacity=2)
        first = self._create_subunit(unit, "104-A")
        self._create_subunit(unit, "104-B")

        with _allow_unit_mutation():
            first.is_active = False
            first.save()

        unit.capacity = 1
        with _allow_unit_mutation():
            unit.save()

        unit.refresh_from_db()
        self.assertEqual(unit.capacity, 1)
        self.assertEqual(unit.subunits.filter(is_active=True).count(), 1)
