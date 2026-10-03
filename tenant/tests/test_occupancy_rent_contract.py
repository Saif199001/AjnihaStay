from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.services import create_property
from tenant.models import Occupancy
from tenant.serializers import OccupancySerializer
from tenant.services import create_occupancy
from unit.services import create_unit


class OccupancyRentContractTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "occupancy-rent-contract@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Occupancy Rent Contract Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Occupancy Rent Contract Property",
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
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )

        from tenant.services import create_tenant

        self.tenant = create_tenant(
            self.owner,
            self.workspace,
            {
                "full_name": "Rent Contract Tenant",
                "phone": "9876543210",
                "permanent_address": "Test Address",
            },
            MultiValueDict(),
        )

    def occupancy_data(self, rent):
        return {
            "tenant": self.tenant.pk,
            "unit": self.unit.pk,
            "rent": rent,
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": date(2026, 10, 1),
            "check_out_date": None,
            "next_due_date": date(2026, 11, 1),
            "security_deposit": Decimal("10000"),
            "deposit_paid": False,
        }

    def test_positive_rent_is_accepted(self):
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(Decimal("10000")),
        )
        self.assertEqual(occupancy.rent, Decimal("10000"))

    def test_zero_rent_is_rejected_by_service(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Rent must be greater than zero",
        ):
            create_occupancy(
                self.owner,
                self.workspace,
                self.occupancy_data(Decimal("0")),
            )

    def test_zero_rent_is_rejected_by_serializer(self):
        serializer = OccupancySerializer(data=self.occupancy_data(Decimal("0")))
        self.assertFalse(serializer.is_valid())
        self.assertIn("rent", serializer.errors)
        self.assertEqual(
            serializer.errors["rent"][0],
            "Rent must be greater than zero",
        )

    def test_negative_rent_is_rejected_by_service(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Rent must be greater than zero",
        ):
            create_occupancy(
                self.owner,
                self.workspace,
                self.occupancy_data(Decimal("-1")),
            )

    def test_model_constraint_rejects_zero_rent(self):
        occupancy = Occupancy(
            tenant=self.tenant,
            unit=self.unit,
            rent=Decimal("0"),
            billing_type="advance",
            billing_cycle="monthly",
            check_in_date=date(2026, 10, 1),
            next_due_date=date(2026, 11, 1),
        )

        with self.assertRaises(ValidationError):
            occupancy.validate_constraints()
