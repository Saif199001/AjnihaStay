from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .models import Occupancy, Tenant
from .services import create_occupancy


class OccupancyServiceDefaultsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("phase2d-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Phase 2D Workspace",
            slug="phase2d-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Phase 2D Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="201",
            rent=Decimal("10000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Phase 2D Tenant",
            phone="9999999998",
            permanent_address="Delhi",
        )

    def occupancy_data(self):
        return {
            "tenant": self.tenant,
            "unit": self.unit,
            "rent": Decimal("10000.00"),
            "check_in_date": date(2026, 9, 1),
            "next_due_date": date(2026, 10, 1),
        }

    def test_omitted_billing_fields_use_model_defaults(self):
        occupancy = create_occupancy(self.owner, self.workspace, self.occupancy_data())

        self.assertEqual(occupancy.billing_type, "advance")
        self.assertEqual(occupancy.billing_cycle, "monthly")
        self.assertEqual(occupancy.invoices.count(), 1)

    def test_none_billing_fields_do_not_override_defaults(self):
        data = self.occupancy_data()
        data["billing_type"] = None
        data["billing_cycle"] = None

        occupancy = create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(occupancy.billing_type, "advance")
        self.assertEqual(occupancy.billing_cycle, "monthly")

    def test_explicit_billing_values_are_preserved(self):
        data = self.occupancy_data()
        data["billing_type"] = "arrears"
        data["billing_cycle"] = "daily"

        occupancy = create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(occupancy.billing_type, "arrears")
        self.assertEqual(occupancy.billing_cycle, "daily")

    def test_invalid_billing_values_are_rejected_by_service(self):
        data = self.occupancy_data()
        data["billing_type"] = "invalid"
        data["billing_cycle"] = "invalid"

        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(Occupancy.objects.count(), 0)
