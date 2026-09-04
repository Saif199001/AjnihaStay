from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Occupancy, Tenant
from .services import create_occupancy


class OccupancyServiceDefaultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("service-defaults@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Service Defaults",
            slug="service-defaults",
            owner=self.user,
        )
        Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")
        self.property = Property.objects.create(
            owner=self.user,
            workspace=self.workspace,
            name="Defaults Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="101",
            rent=Decimal("10000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.user,
            workspace=self.workspace,
            full_name="Defaults Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )

    def base_data(self):
        return {
            "tenant": self.tenant.id,
            "unit": self.unit.id,
            "rent": Decimal("10000.00"),
            "check_in_date": date(2026, 9, 1),
            "next_due_date": date(2026, 10, 1),
        }

    def test_missing_billing_fields_use_service_defaults(self):
        occupancy = create_occupancy(self.user, self.workspace, self.base_data())

        self.assertEqual(occupancy.billing_type, "advance")
        self.assertEqual(occupancy.billing_cycle, "monthly")
        self.assertEqual(occupancy.security_deposit, Decimal("0.00"))
        self.assertFalse(occupancy.deposit_paid)
        self.assertEqual(occupancy.invoices.count(), 1)

    def test_blank_billing_fields_use_service_defaults(self):
        data = self.base_data()
        data["billing_type"] = ""
        data["billing_cycle"] = ""

        occupancy = create_occupancy(self.user, self.workspace, data)

        self.assertEqual(occupancy.billing_type, "advance")
        self.assertEqual(occupancy.billing_cycle, "monthly")

    def test_explicit_billing_values_are_preserved(self):
        data = self.base_data()
        data["billing_type"] = "arrears"
        data["billing_cycle"] = "daily"

        occupancy = create_occupancy(self.user, self.workspace, data)

        self.assertEqual(occupancy.billing_type, "arrears")
        self.assertEqual(occupancy.billing_cycle, "daily")

    def test_defaulted_service_values_are_persisted_not_just_in_memory(self):
        occupancy = create_occupancy(self.user, self.workspace, self.base_data())
        saved = Occupancy.objects.get(pk=occupancy.pk)

        self.assertEqual(saved.billing_type, "advance")
        self.assertEqual(saved.billing_cycle, "monthly")
