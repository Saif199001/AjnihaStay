from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from leasing.cancellation_service import cancel_lease
from leasing.expiry_service import expire_lease
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseLifecycleEvent
from leasing.models import Lease
from leasing.termination_service import terminate_lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class CancellationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="cancellation-owner@example.com", password="pass"
        )
        self.manager = User.objects.create_user(
            email="cancellation-manager@example.com", password="pass"
        )
        self.workspace = Workspace.objects.create(
            name="Cancellation Workspace",
            slug="cancellation-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner", is_active=True
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.manager, role="manager", is_active=True
        )
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Cancellation Property",
            property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001",
        )
        self.unit = Unit.objects.create(
            property=self.property, unit_type="flat", unit_number="101", rent=Decimal("12000.00")
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Cancellation Tenant",
            phone="9999999999", email="cancellation-tenant@example.com",
            permanent_address="Lucknow, Uttar Pradesh",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant, unit=self.unit, rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True,
        )

    def _lease(self, **overrides):
        data = {
            "occupancy": self.occupancy, "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31), "rent_amount": Decimal("12000.00"),
            "security_deposit": Decimal("24000.00"),
        }
        data.update(overrides)
        return create_lease(self.manager, self.workspace, data)

    def _pending_lease(self, **overrides):
        lease = self._lease(**overrides)
        return transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)

    def _active_lease(self, **overrides):
        lease = self._pending_lease(**overrides)
        return transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def _separate_occupancy(self, number, email, full_name):
        unit = Unit.objects.create(
            property=self.property,
            unit_type="flat",
            unit_number=number,
            rent=Decimal("12000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name=full_name,
            phone=f"99999999{number[-2:]}",
            email=email,
            permanent_address="Lucknow, Uttar Pradesh",
        )
        return Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31),
            next_due_date=date(2026, 1, 1),
            is_active=True,
        )

    def test_cancellation_records_reason_effective_date_actor_and_status_transition(self):
        lease = self._lease()
        effective_date = timezone.localdate()
        cancelled = cancel_lease(self.manager, self.workspace, lease.id, reason="Owner cancelled before signing", effective_date=effective_date)
        self.assertEqual(cancelled.status, Lease.STATUS_CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED)
        self.assertEqual(event.actor_id, self.manager.id)
        self.assertEqual(event.effective_date, effective_date)
        self.assertEqual(event.metadata["reason"], "Owner cancelled before signing")
        self.assertEqual(event.metadata["from_status"], Lease.STATUS_DRAFT)
        self.assertEqual(event.metadata["to_status"], Lease.STATUS_CANCELLED)

    def test_pending_signature_lease_can_be_cancelled(self):
        lease = self._pending_lease()
        cancelled = cancel_lease(self.manager, self.workspace, lease.id, reason="Applicant withdrew")
        self.assertEqual(cancelled.status, Lease.STATUS_CANCELLED)
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED)
        self.assertEqual(event.metadata["from_status"], Lease.STATUS_PENDING_SIGNATURE)

    def test_cancellation_defaults_effective_date_to_today(self):
        lease = self._lease()
        cancel_lease(self.manager, self.workspace, lease.id, reason="No longer needed")
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_type=LeaseLifecycleEvent.EVENT_CANCELLED)
        self.assertEqual(event.effective_date, timezone.localdate())

    def test_reason_is_required_and_limited_to_model_reason_length(self):
        lease = self._lease()
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, lease.id, reason="   ")
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, lease.id, reason="x" * 501)
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)

    def test_future_effective_date_is_rejected(self):
        lease = self._lease()
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, lease.id, reason="Future cancellation", effective_date=timezone.localdate() + timedelta(days=1))
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)

    def test_active_expired_and_terminated_leases_cannot_be_cancelled(self):
        active = self._active_lease()
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, active.id, reason="Too late")

        expired_occupancy = self._separate_occupancy(
            "102", "cancellation-expired@example.com", "Cancellation Expired Tenant"
        )
        expired = self._active_lease(occupancy=expired_occupancy, end_date=timezone.localdate())
        expire_lease(self.manager, self.workspace, expired.id)
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, expired.id, reason="Already expired")

        terminated_occupancy = self._separate_occupancy(
            "103", "cancellation-terminated@example.com", "Cancellation Terminated Tenant"
        )
        terminated = self._active_lease(occupancy=terminated_occupancy)
        terminate_lease(self.manager, self.workspace, terminated.id, reason="Already terminated")
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, terminated.id, reason="Already terminated")

    def test_repeated_identical_cancellation_is_idempotent(self):
        lease = self._lease()
        effective_date = timezone.localdate()
        first = cancel_lease(self.manager, self.workspace, lease.id, reason="Mutual cancellation", effective_date=effective_date)
        first_cancelled_at = first.cancelled_at
        second = cancel_lease(self.manager, self.workspace, lease.id, reason="Mutual cancellation", effective_date=effective_date)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.cancelled_at, first_cancelled_at)
        self.assertEqual(LeaseLifecycleEvent.objects.filter(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED).count(), 1)

    def test_conflicting_retry_cannot_rewrite_cancellation_history(self):
        lease = self._lease()
        cancel_lease(self.manager, self.workspace, lease.id, reason="Original reason")
        with self.assertRaises(ValidationError):
            cancel_lease(self.manager, self.workspace, lease.id, reason="Changed reason")
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED)
        self.assertEqual(event.metadata["reason"], "Original reason")

    def test_cancellation_does_not_change_occupancy(self):
        lease = self._lease()
        before = self.occupancy.is_active
        cancel_lease(self.manager, self.workspace, lease.id, reason="Not proceeding")
        self.occupancy.refresh_from_db()
        self.assertEqual(self.occupancy.is_active, before)

    def test_cross_workspace_and_insufficient_permission_are_rejected(self):
        lease = self._lease()
        other_owner = User.objects.create_user(email="cancellation-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="Other Cancellation Workspace", slug="other-cancellation-workspace", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            cancel_lease(other_owner, other_workspace, lease.id, reason="Wrong workspace")
        member = User.objects.create_user(email="cancellation-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        with self.assertRaises(PermissionDenied):
            cancel_lease(member, self.workspace, lease.id, reason="Insufficient permission")
