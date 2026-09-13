from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent
from leasing.models import Lease
from leasing.termination_service import terminate_lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class TerminationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="termination-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="termination-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(
            name="Termination Workspace", slug="termination-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Termination Property",
            property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001",
        )
        self.unit = Unit.objects.create(
            property=self.property, unit_type="flat", unit_number="101", rent=Decimal("12000.00")
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Termination Tenant",
            phone="9999999999", email="termination-tenant@example.com",
            permanent_address="Lucknow, Uttar Pradesh",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant, unit=self.unit, rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True,
        )

    def _active_lease(self):
        lease = create_lease(self.manager, self.workspace, {
            "occupancy": self.occupancy,
            "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31),
            "rent_amount": Decimal("12000.00"), "security_deposit": Decimal("24000.00"),
        })
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        return transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def test_termination_records_reason_effective_date_actor_and_contract_version(self):
        lease = self._active_lease()
        effective_date = timezone.localdate()
        terminated = terminate_lease(
            self.manager, self.workspace, lease.id,
            reason="Tenant requested early move-out", effective_date=effective_date,
        )
        self.assertEqual(terminated.status, Lease.STATUS_TERMINATED)
        self.assertIsNotNone(terminated.terminated_at)
        event = LeaseLifecycleEvent.objects.get(
            lease=lease, event_key=LeaseLifecycleEvent.EVENT_TERMINATED
        )
        self.assertEqual(event.actor_id, self.manager.id)
        self.assertEqual(event.effective_date, effective_date)
        self.assertEqual(event.metadata["reason"], "Tenant requested early move-out")
        self.assertEqual(event.metadata["from_status"], Lease.STATUS_ACTIVE)
        self.assertEqual(event.metadata["to_status"], Lease.STATUS_TERMINATED)
        version = LeaseContractVersion.objects.get(lease=lease, version_number=1)
        self.assertEqual(event.metadata["contract_version_id"], version.id)
        self.assertEqual(event.metadata["contract_version_number"], 1)

    def test_termination_is_distinct_from_expiry_and_can_happen_before_contract_end(self):
        lease = self._active_lease()
        effective_date = timezone.localdate()
        terminated = terminate_lease(
            self.manager, self.workspace, lease.id,
            reason="Mutual agreement", effective_date=effective_date,
        )
        self.assertEqual(terminated.status, Lease.STATUS_TERMINATED)
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_type=LeaseLifecycleEvent.EVENT_TERMINATED)
        self.assertEqual(event.effective_date, effective_date)
        self.assertNotEqual(event.effective_date, lease.end_date)

    def test_termination_defaults_effective_date_to_today(self):
        lease = self._active_lease()
        terminate_lease(self.manager, self.workspace, lease.id, reason="Early exit")
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_type=LeaseLifecycleEvent.EVENT_TERMINATED)
        self.assertEqual(event.effective_date, timezone.localdate())

    def test_blank_or_overlong_reason_is_rejected(self):
        lease = self._active_lease()
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, lease.id, reason="   ")
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, lease.id, reason="x" * 501)
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)

    def test_invalid_effective_dates_are_rejected(self):
        lease = self._active_lease()
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, lease.id, reason="Past", effective_date=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, lease.id, reason="Future", effective_date=timezone.localdate() + timedelta(days=1))

    def test_only_active_leases_can_terminate(self):
        draft = create_lease(self.manager, self.workspace, {
            "occupancy": self.occupancy, "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31),
            "rent_amount": Decimal("12000.00"), "security_deposit": Decimal("24000.00"),
        })
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, draft.id, reason="Not active")

        active = self._active_lease()
        active.status = Lease.STATUS_EXPIRED
        active.save()
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, active.id, reason="Already expired")

    def test_repeated_identical_termination_is_idempotent(self):
        lease = self._active_lease()
        effective_date = timezone.localdate()
        first = terminate_lease(self.manager, self.workspace, lease.id, reason="Mutual agreement", effective_date=effective_date)
        first_terminated_at = first.terminated_at
        second = terminate_lease(self.manager, self.workspace, lease.id, reason="Mutual agreement", effective_date=effective_date)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.terminated_at, first_terminated_at)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(lease=lease, event_key=LeaseLifecycleEvent.EVENT_TERMINATED).count(), 1
        )

    def test_terminated_history_is_immutable_on_retry(self):
        lease = self._active_lease()
        terminate_lease(self.manager, self.workspace, lease.id, reason="Original reason")
        with self.assertRaises(ValidationError):
            terminate_lease(self.manager, self.workspace, lease.id, reason="Changed reason")
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(lease=lease, event_key=LeaseLifecycleEvent.EVENT_TERMINATED).count(), 1
        )

    def test_occupancy_and_contract_version_are_unchanged(self):
        lease = self._active_lease()
        version = LeaseContractVersion.objects.get(lease=lease, version_number=1)
        occupancy_status = self.occupancy.is_active
        terminate_lease(self.manager, self.workspace, lease.id, reason="Mutual agreement")
        self.occupancy.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(self.occupancy.is_active, occupancy_status)
        self.assertEqual(version.end_date, date(2026, 12, 31))
        self.assertEqual(version.rent_amount, Decimal("12000.00"))

    def test_cross_workspace_and_insufficient_permission_are_rejected(self):
        lease = self._active_lease()
        other_owner = User.objects.create_user(email="termination-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-termination-workspace", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            terminate_lease(other_owner, other_workspace, lease.id, reason="Wrong workspace")

        member = User.objects.create_user(email="termination-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        with self.assertRaises(PermissionDenied):
            terminate_lease(member, self.workspace, lease.id, reason="Insufficient permission")
