from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import User
from leasing.expiry_service import expire_lease
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseExpiryServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="expiry-owner@example.com", password="pass"
        )
        self.manager = User.objects.create_user(
            email="expiry-manager@example.com", password="pass"
        )
        self.workspace = Workspace.objects.create(
            name="Expiry Workspace", slug="expiry-workspace", owner=self.owner
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner", is_active=True
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.manager, role="manager", is_active=True
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Expiry Property",
            property_type="flat",
            address="Address",
            city="Lucknow",
            state="UP",
            pincode="226001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="flat",
            unit_number="E-101",
            rent=Decimal("12000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Expiry Tenant",
            phone="8888888888",
            email="expiry-tenant@example.com",
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

    def _active_lease(self, end_date=date(2026, 12, 31)):
        lease = create_lease(
            self.manager,
            self.workspace,
            {
                "occupancy": self.occupancy,
                "start_date": date(2026, 1, 1),
                "end_date": end_date,
                "rent_amount": Decimal("12000.00"),
                "security_deposit": Decimal("24000.00"),
            },
        )
        transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE
        )
        return transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE
        )

    def test_expiry_changes_lease_only_and_records_effective_contract_end(self):
        lease = self._active_lease()
        occupancy_id = lease.occupancy_id
        version = LeaseContractVersion.objects.get(lease=lease, version_number=1)

        expired = expire_lease(self.manager, self.workspace, lease.id)

        self.assertEqual(expired.status, Lease.STATUS_EXPIRED)
        self.assertEqual(expired.occupancy_id, occupancy_id)
        self.occupancy.refresh_from_db()
        self.assertTrue(self.occupancy.is_active)
        event = LeaseLifecycleEvent.objects.get(
            lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
        )
        self.assertEqual(event.actor_id, self.manager.id)
        self.assertEqual(event.effective_date, version.end_date)
        self.assertEqual(event.metadata["contract_version_id"], version.id)
        self.assertEqual(event.metadata["contract_version_number"], 1)
        self.assertEqual(event.metadata["from_status"], Lease.STATUS_ACTIVE)
        self.assertEqual(event.metadata["to_status"], Lease.STATUS_EXPIRED)

    def test_expiry_is_idempotent_and_does_not_duplicate_event(self):
        lease = self._active_lease()
        first = expire_lease(self.manager, self.workspace, lease.id)
        second = expire_lease(
            self.manager,
            self.workspace,
            lease.id,
            effective_date=date(1900, 1, 1),
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
            ).count(),
            1,
        )

    def test_expiry_requires_active_status(self):
        lease = create_lease(
            self.manager,
            self.workspace,
            {
                "occupancy": self.occupancy,
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "rent_amount": Decimal("12000.00"),
                "security_deposit": Decimal("24000.00"),
            },
        )
        with self.assertRaises(ValidationError):
            expire_lease(self.manager, self.workspace, lease.id)

    def test_expiry_rejects_early_effective_date(self):
        lease = self._active_lease()
        with self.assertRaises(ValidationError):
            expire_lease(
                self.manager,
                self.workspace,
                lease.id,
                effective_date=date(2026, 12, 30),
            )
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)
        self.assertFalse(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
            ).exists()
        )

    def test_expiry_uses_latest_contract_version_after_renewal(self):
        lease = self._active_lease()
        version_two = LeaseContractVersion.objects.create(
            lease=lease,
            workspace=self.workspace,
            version_number=2,
            predecessor=LeaseContractVersion.objects.get(lease=lease, version_number=1),
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            rent_amount=Decimal("13000.00"),
            security_deposit=Decimal("24000.00"),
            notice_period_days=30,
            terms={"renewed": True},
            agreement_reference="RENEWED-001",
            created_by=self.manager,
        )

        expire_lease(self.manager, self.workspace, lease.id)
        event = LeaseLifecycleEvent.objects.get(
            lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
        )
        self.assertEqual(event.effective_date, version_two.end_date)
        self.assertEqual(event.metadata["contract_version_id"], version_two.id)
        self.assertEqual(event.metadata["contract_version_number"], 2)

    def test_expiry_rejects_cross_workspace_and_insufficient_role(self):
        lease = self._active_lease()
        member = User.objects.create_user(
            email="expiry-member@example.com", password="pass"
        )
        Membership.objects.create(
            workspace=self.workspace, user=member, role="member", is_active=True
        )
        with self.assertRaises(PermissionDenied):
            expire_lease(member, self.workspace, lease.id)

        other_owner = User.objects.create_user(
            email="expiry-other@example.com", password="pass"
        )
        other_workspace = Workspace.objects.create(
            name="Other Expiry", slug="other-expiry-workspace", owner=other_owner
        )
        Membership.objects.create(
            workspace=other_workspace, user=other_owner, role="owner", is_active=True
        )
        with self.assertRaises(ValidationError):
            expire_lease(other_owner, other_workspace, lease.id)
