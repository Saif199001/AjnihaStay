from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase

from accounts.models import User
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="lease-owner", password="pass")
        self.workspace = Workspace.objects.create(name="Lease Workspace", owner=self.owner)
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role="owner",
            is_active=True,
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Lease Property",
            property_type="flat",
            address="Address",
            city="Lucknow",
            state="UP",
            pincode="226001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="flat",
            unit_number="101",
            rent=Decimal("12000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Tenant One",
            email="tenant@example.com",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31),
            next_due_date=date(2026, 1, 1),
            is_active=True,
        )

    def test_lease_uses_occupancy_as_tenant_source(self):
        lease = Lease.objects.create(
            workspace=self.workspace,
            occupancy=self.occupancy,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent_amount=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            created_by=self.owner,
        )
        self.assertEqual(lease.occupancy.tenant_id, self.tenant.id)
        self.assertEqual(self.occupancy.lease_id, lease.id)

    def test_lease_rejects_invalid_dates(self):
        with self.assertRaises(ValidationError):
            Lease.objects.create(
                workspace=self.workspace,
                occupancy=self.occupancy,
                start_date=date(2026, 12, 31),
                end_date=date(2026, 1, 1),
                rent_amount=Decimal("12000.00"),
                created_by=self.owner,
            )

    def test_lease_rejects_cross_workspace_occupancy(self):
        other_owner = User.objects.create_user(username="other-owner", password="pass")
        other_workspace = Workspace.objects.create(name="Other Workspace", owner=other_owner)
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role="owner",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            Lease.objects.create(
                workspace=other_workspace,
                occupancy=self.occupancy,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                rent_amount=Decimal("12000.00"),
                created_by=other_owner,
            )

    def test_lease_index_names_are_explicit_and_short(self):
        indexes = {index.name for index in Lease._meta.indexes}
        self.assertEqual(
            indexes,
            {
                "leasing_leas_workspa_9a1c2b_idx",
                "leasing_leas_workspa_4f7d8e_idx",
                "leasing_leas_workspa_6b2e5a_idx",
            },
        )
        self.assertTrue(all(len(name) <= 63 for name in indexes))

    def test_postgres_rls_policy_exists_when_available(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL RLS is not available on this database")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE oid = 'leasing_lease'::regclass
                """
            )
            self.assertEqual(cursor.fetchone(), (True, True))
