from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice
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

    def test_invoice_failure_rolls_back_occupancy_creation(self):
        data = self.occupancy_data()

        with patch.object(Invoice.objects, "create", side_effect=RuntimeError("invoice failure")):
            with self.assertRaises(RuntimeError):
                create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(Occupancy.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_cross_workspace_tenant_is_rejected(self):
        other_owner = User.objects.create_user("phase2d-other-owner@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Workspace",
            slug="phase2d-other-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner")
        other_tenant = Tenant.objects.create(
            owner=other_owner,
            workspace=other_workspace,
            full_name="Other Tenant",
            phone="9999999997",
            permanent_address="Noida",
        )
        data = self.occupancy_data()
        data["tenant"] = other_tenant

        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(Occupancy.objects.count(), 0)

    def test_cross_workspace_unit_is_rejected(self):
        other_owner = User.objects.create_user("phase2d-unit-owner@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Unit Workspace",
            slug="phase2d-other-unit-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner")
        other_property = Property.objects.create(
            owner=other_owner,
            workspace=other_workspace,
            name="Other Property",
            property_type="pg",
            address="Noida",
            city="Noida",
            state="UP",
            pincode="201301",
        )
        other_unit = Unit.objects.create(
            property=other_property,
            unit_type="room",
            unit_number="301",
            rent=Decimal("12000.00"),
        )
        data = self.occupancy_data()
        data["unit"] = other_unit

        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(Occupancy.objects.count(), 0)

    def test_subunit_must_belong_to_selected_unit(self):
        from unit.models import SubUnit

        subunit = SubUnit.objects.create(
            unit=self.unit,
            subunit_number="A",
            rent=Decimal("5000.00"),
        )
        other_unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="202",
            rent=Decimal("10000.00"),
        )
        data = self.occupancy_data()
        data["unit"] = other_unit
        data["subunit"] = subunit

        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

        self.assertEqual(Occupancy.objects.count(), 0)
