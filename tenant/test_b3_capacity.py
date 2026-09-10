from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase

from accounts.models import User
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Occupancy, Tenant
from .services import create_occupancy


class OccupancyCapacityConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user("b3-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="B3 Workspace",
            slug="b3-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role="owner",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="B3 Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="B3-101",
            rent=Decimal("10000.00"),
            capacity=1,
        )
        self.tenant_a = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="B3 Tenant A",
            phone="9999999901",
            permanent_address="Delhi",
        )
        self.tenant_b = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="B3 Tenant B",
            phone="9999999902",
            permanent_address="Delhi",
        )

    def occupancy_data(self, tenant):
        return {
            "tenant": tenant.id,
            "unit": self.unit.id,
            "rent": Decimal("10000.00"),
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": date(2026, 9, 1),
            "next_due_date": date(2026, 10, 1),
        }

    def test_capacity_reduction_cannot_violate_existing_overlap(self):
        self.unit.capacity = 2
        self.unit.save()
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant_a))
        data = self.occupancy_data(self.tenant_b)
        data["check_in_date"] = date(2026, 9, 15)
        data["next_due_date"] = date(2026, 10, 15)
        create_occupancy(self.owner, self.workspace, data)

        self.unit.refresh_from_db()
        self.unit.capacity = 1
        with self.assertRaisesMessage(
            ValidationError,
            "Unit capacity cannot be reduced below active overlapping occupancy count",
        ):
            self.unit.save()

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.capacity, 2)

    def test_capacity_reduction_allows_non_overlapping_occupancies(self):
        self.unit.capacity = 2
        self.unit.save()
        create_occupancy(self.owner, self.workspace, self.occupancy_data(self.tenant_a))
        data = self.occupancy_data(self.tenant_b)
        data["check_in_date"] = date(2026, 10, 2)
        data["check_out_date"] = date(2026, 10, 31)
        data["next_due_date"] = date(2026, 11, 1)
        create_occupancy(self.owner, self.workspace, data)

        self.unit.refresh_from_db()
        self.unit.capacity = 1
        self.unit.save()

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.capacity, 1)

    def test_concurrent_occupancy_creation_never_exceeds_capacity(self):
        barrier = Barrier(2)

        def attempt(tenant):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_occupancy(self.owner, self.workspace, self.occupancy_data(tenant))
                return "success"
            except ValidationError:
                return "validation_error"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (self.tenant_a, self.tenant_b)))

        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("validation_error"), 1)
        self.assertEqual(
            Occupancy.objects.filter(
                unit=self.unit,
                subunit__isnull=True,
                is_active=True,
            ).count(),
            1,
        )
