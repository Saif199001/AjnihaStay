from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.services import create_user_account
from properties.services import create_property
from django.utils.datastructures import MultiValueDict

from unit.models import SubUnit, Unit, _allow_unit_mutation
from unit.serializers import SubUnitSerializer, UnitSerializer
from unit.services import create_subunit, create_unit


class RentContractTests(TestCase):
    def setUp(self):
        self.user = create_user_account(
            "rent-contract@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Rent Contract Workspace",
        )
        self.workspace = self.user.owned_workspaces.get()
        self.property = create_property(
            self.user,
            self.workspace,
            {
                "owner": self.user,
                "name": "Rent Contract Property",
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

    def unit_data(self, number="101", rent=Decimal("10000")):
        return {
            "property": self.property,
            "unit_number": number,
            "unit_type": "room",
            "rent": rent,
            "capacity": 2,
            "description": "",
        }

    def subunit_data(self, unit, number="101-A", rent=Decimal("5000")):
        return {
            "unit": unit,
            "subunit_number": number,
            "rent": rent,
        }

    def test_unit_service_rejects_missing_rent(self):
        data = self.unit_data()
        data.pop("rent")
        with self.assertRaisesMessage(ValidationError, "Rent is required"):
            create_unit(self.user, self.workspace, data)

    def test_unit_service_rejects_empty_rent(self):
        with self.assertRaisesMessage(ValidationError, "Rent is required"):
            create_unit(self.user, self.workspace, self.unit_data(rent=""))

    def test_unit_service_rejects_zero_rent(self):
        with self.assertRaisesMessage(ValidationError, "Rent must be greater than 0"):
            create_unit(self.user, self.workspace, self.unit_data(rent=Decimal("0")))

    def test_unit_service_rejects_negative_rent(self):
        with self.assertRaisesMessage(ValidationError, "Rent must be greater than 0"):
            create_unit(self.user, self.workspace, self.unit_data(rent=Decimal("-1")))

    def test_unit_service_accepts_positive_rent(self):
        unit = create_unit(
            self.user,
            self.workspace,
            self.unit_data(rent=Decimal("1")),
        )
        self.assertEqual(unit.rent, Decimal("1.00"))

    def test_subunit_service_rejects_missing_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        data = self.subunit_data(unit)
        data.pop("rent")
        with self.assertRaisesMessage(ValidationError, "Rent is required"):
            create_subunit(self.user, self.workspace, data)

    def test_subunit_service_rejects_empty_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        with self.assertRaisesMessage(ValidationError, "Rent is required"):
            create_subunit(self.user, self.workspace, self.subunit_data(unit, rent=""))

    def test_subunit_service_rejects_zero_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        with self.assertRaisesMessage(ValidationError, "Rent must be greater than 0"):
            create_subunit(
                self.user,
                self.workspace,
                self.subunit_data(unit, rent=Decimal("0")),
            )

    def test_subunit_service_rejects_negative_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        with self.assertRaisesMessage(ValidationError, "Rent must be greater than 0"):
            create_subunit(
                self.user,
                self.workspace,
                self.subunit_data(unit, rent=Decimal("-1")),
            )

    def test_subunit_service_accepts_positive_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        subunit = create_subunit(
            self.user,
            self.workspace,
            self.subunit_data(unit, rent=Decimal("1")),
        )
        self.assertEqual(subunit.rent, Decimal("1.00"))

    def test_unit_model_rejects_missing_rent(self):
        unit = Unit(**self.unit_data(rent=None))
        with self.assertRaisesMessage(ValidationError, "Unit rent is required"):
            unit.clean()

    def test_unit_model_rejects_zero_rent(self):
        unit = Unit(**self.unit_data(rent=Decimal("0")))
        with self.assertRaisesMessage(ValidationError, "Unit rent must be greater than 0"):
            unit.clean()

    def test_unit_model_rejects_negative_rent(self):
        unit = Unit(**self.unit_data(rent=Decimal("-1")))
        with self.assertRaisesMessage(ValidationError, "Unit rent must be greater than 0"):
            unit.clean()

    def test_subunit_model_rejects_missing_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        subunit = SubUnit(unit=unit, subunit_number="101-A", rent=None)
        with self.assertRaisesMessage(ValidationError, "SubUnit rent is required"):
            subunit.clean()

    def test_subunit_model_rejects_zero_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        subunit = SubUnit(
            unit=unit,
            subunit_number="101-A",
            rent=Decimal("0"),
        )
        with self.assertRaisesMessage(ValidationError, "SubUnit rent must be greater than 0"):
            subunit.clean()

    def test_subunit_model_rejects_negative_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        subunit = SubUnit(
            unit=unit,
            subunit_number="101-A",
            rent=Decimal("-1"),
        )
        with self.assertRaisesMessage(ValidationError, "SubUnit rent must be greater than 0"):
            subunit.clean()

    def test_unit_serializer_requires_positive_rent(self):
        for rent in (None, Decimal("0"), Decimal("-1")):
            data = self.unit_data(rent=rent)
            serializer = UnitSerializer(data=data)
            self.assertFalse(serializer.is_valid())
            self.assertIn("rent", serializer.errors)

    def test_unit_serializer_accepts_positive_rent(self):
        serializer = UnitSerializer(data=self.unit_data(rent=Decimal("1")))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_subunit_serializer_requires_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        data = self.subunit_data(unit)
        data.pop("rent")
        serializer = SubUnitSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("rent", serializer.errors)

    def test_subunit_serializer_requires_positive_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        for rent in (Decimal("0"), Decimal("-1")):
            serializer = SubUnitSerializer(
                data=self.subunit_data(unit, number=f"101-{rent}", rent=rent)
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn("rent", serializer.errors)

    def test_subunit_serializer_accepts_positive_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        serializer = SubUnitSerializer(
            data=self.subunit_data(unit, rent=Decimal("1"))
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_unit_db_constraint_rejects_zero_rent(self):
        candidate = Unit(**self.unit_data(number="102", rent=Decimal("0")))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with _allow_unit_mutation():
                    Unit.objects.bulk_create([candidate])

    def test_unit_db_constraint_rejects_negative_rent(self):
        candidate = Unit(**self.unit_data(number="103", rent=Decimal("-1")))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with _allow_unit_mutation():
                    Unit.objects.bulk_create([candidate])

    def test_subunit_db_constraint_rejects_zero_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        candidate = SubUnit(
            unit=unit,
            subunit_number="101-B",
            rent=Decimal("0"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with _allow_unit_mutation():
                    SubUnit.objects.bulk_create([candidate])

    def test_subunit_db_constraint_rejects_negative_rent(self):
        unit = create_unit(self.user, self.workspace, self.unit_data())
        candidate = SubUnit(
            unit=unit,
            subunit_number="101-C",
            rent=Decimal("-1"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with _allow_unit_mutation():
                    SubUnit.objects.bulk_create([candidate])

    def test_active_subunit_total_must_not_exceed_unit_rent(self):
        unit = create_unit(
            self.user,
            self.workspace,
            self.unit_data(rent=Decimal("10000")),
        )
        create_subunit(
            self.user,
            self.workspace,
            self.subunit_data(unit, rent=Decimal("6000")),
        )
        with self.assertRaisesMessage(ValidationError, "Total rent exceeded"):
            create_subunit(
                self.user,
                self.workspace,
                self.subunit_data(unit, number="101-B", rent=Decimal("5000")),
            )
