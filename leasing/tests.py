from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="lease-owner@example.com",
            password="pass",
        )
        self.workspace = Workspace.objects.create(
            name="Lease Workspace",
            slug="lease-workspace",
            owner=self.owner,
        )
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
            full_name="Tenant One",
            phone="9999999999",
            email="tenant@example.com",
            permanent_address="Lucknow, Uttar Pradesh",
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

    def _lease_kwargs(self, **overrides):
        data = {
            "workspace": self.workspace,
            "occupancy": self.occupancy,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "rent_amount": Decimal("12000.00"),
            "security_deposit": Decimal("24000.00"),
            "created_by": self.owner,
        }
        data.update(overrides)
        return data

    def test_lease_uses_occupancy_as_tenant_source_and_reverse_relation(self):
        lease = Lease.objects.create(**self._lease_kwargs())
        self.assertEqual(lease.occupancy.tenant_id, self.tenant.id)
        self.assertEqual(self.occupancy.lease.id, lease.id)

    def test_lease_occupancy_is_one_to_one(self):
        Lease.objects.create(**self._lease_kwargs())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lease.objects.create(**self._lease_kwargs(agreement_number="LEASE-2"))

    def test_lease_related_names_are_contractual(self):
        self.assertEqual(Lease._meta.get_field("workspace").remote_field.related_name, "leases")
        self.assertEqual(Lease._meta.get_field("occupancy").remote_field.related_name, "lease")
        self.assertEqual(Lease._meta.get_field("created_by").remote_field.related_name, "leases_created")
        self.assertEqual(Lease._meta.get_field("updated_by").remote_field.related_name, "leases_updated")

    def test_lease_rejects_invalid_dates(self):
        with self.assertRaises(ValidationError):
            Lease.objects.create(
                **self._lease_kwargs(
                    start_date=date(2026, 12, 31),
                    end_date=date(2026, 1, 1),
                )
            )

    def test_lease_rejects_cross_workspace_occupancy(self):
        other_owner = User.objects.create_user(
            email="other-owner@example.com",
            password="pass",
        )
        other_workspace = Workspace.objects.create(
            name="Other Workspace",
            slug="other-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role="owner",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            Lease.objects.create(
                **self._lease_kwargs(workspace=other_workspace, created_by=other_owner)
            )

    def test_lease_rejects_inactive_creator(self):
        inactive_user = User.objects.create_user(
            email="inactive-lease-creator@example.com",
            password="pass",
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=inactive_user,
            role="manager",
            is_active=False,
        )
        with self.assertRaises(ValidationError):
            Lease.objects.create(**self._lease_kwargs(created_by=inactive_user))

    def test_lease_rejects_invalid_status(self):
        with self.assertRaises(ValidationError):
            Lease.objects.create(**self._lease_kwargs(status="not_a_status"))

    def test_lease_rejects_negative_financial_values(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lease.objects.create(**self._lease_kwargs(rent_amount=Decimal("-1.00")))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lease.objects.create(**self._lease_kwargs(security_deposit=Decimal("-1.00")))

    def test_lease_index_names_are_explicit_and_short(self):
        indexes = {index.name for index in Lease._meta.indexes}
        self.assertEqual(
            indexes,
            {
                "lease_ws_status_idx",
                "lease_ws_start_idx",
                "lease_ws_end_idx",
            },
        )
        self.assertTrue(all(len(name) <= 30 for name in indexes))

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
            cursor.execute(
                """
                SELECT polname
                FROM pg_policy
                WHERE polrelid = 'leasing_lease'::regclass
                """
            )
            self.assertIn(
                "workspace_isolation_leasinglease",
                {row[0] for row in cursor.fetchall()},
            )
