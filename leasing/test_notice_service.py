from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseLifecycleEvent, LeaseNotice
from leasing.notice_service import create_notice, transition_notice
from leasing.models import Lease
from leasing.termination_service import terminate_lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseNoticeServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="notice-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="notice-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="Notice Workspace", slug="notice-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        prop = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Notice Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=prop, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Notice Tenant", phone="9999999999", email="notice-tenant@example.com", permanent_address="Lucknow, Uttar Pradesh")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True)
        lease = create_lease(self.manager, self.workspace, {"occupancy": occupancy, "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "rent_amount": Decimal("12000.00"), "security_deposit": Decimal("24000.00")})
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.lease = transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def _create(self, **overrides):
        data = {"notice_date": timezone.localdate(), "effective_date": timezone.localdate() + timedelta(days=7), "notice_type": LeaseNotice.TYPE_TERMINATION, "reason": "Contractual notice"}
        data.update(overrides)
        return create_notice(self.manager, self.workspace, self.lease.id, **data)

    def test_create_notice_records_draft_and_history(self):
        notice = self._create()
        self.assertEqual(notice.status, LeaseNotice.STATUS_DRAFT)
        event = LeaseLifecycleEvent.objects.get(lease=self.lease, event_key=f"notice:{notice.id}:created")
        self.assertEqual(event.event_type, LeaseLifecycleEvent.EVENT_NOTICE)
        self.assertEqual(event.actor_id, self.manager.id)
        self.assertEqual(event.metadata["status"], LeaseNotice.STATUS_DRAFT)

    def test_notice_lifecycle_is_ordered(self):
        notice = self._create(effective_date=timezone.localdate())
        notice = transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_ISSUED)
        notice = transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_EFFECTIVE)
        notice = transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_COMPLETED)
        self.assertEqual(notice.status, LeaseNotice.STATUS_COMPLETED)
        self.assertEqual(LeaseLifecycleEvent.objects.filter(lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_NOTICE).count(), 4)

    def test_future_effective_notice_cannot_become_effective_early(self):
        notice = self._create()
        transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_ISSUED)
        with self.assertRaises(ValidationError):
            transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_EFFECTIVE)
        notice.refresh_from_db()
        self.assertEqual(notice.status, LeaseNotice.STATUS_ISSUED)

    def test_withdrawal_is_terminal_and_idempotent(self):
        notice = self._create()
        first = transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_WITHDRAWN)
        second = transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_WITHDRAWN)
        self.assertEqual(first.id, second.id)
        with self.assertRaises(ValidationError):
            transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_ISSUED)

    def test_invalid_dates_reason_and_state_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(notice_date=timezone.localdate() + timedelta(days=1))
        with self.assertRaises(ValidationError):
            self._create(effective_date=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            self._create(reason="   ")

        terminate_lease(self.manager, self.workspace, self.lease.id, reason="No longer active", effective_date=timezone.localdate())
        with self.assertRaises(ValidationError):
            create_notice(self.manager, self.workspace, self.lease.id, notice_date=timezone.localdate(), effective_date=timezone.localdate(), notice_type=LeaseNotice.TYPE_OTHER, reason="Invalid source")

    def test_cross_workspace_and_member_permissions_are_rejected(self):
        other_owner = User.objects.create_user(email="notice-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="Other Notice", slug="other-notice", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            create_notice(other_owner, other_workspace, self.lease.id, notice_date=timezone.localdate(), effective_date=timezone.localdate(), notice_type=LeaseNotice.TYPE_OTHER, reason="Wrong workspace")
        member = User.objects.create_user(email="notice-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        with self.assertRaises(PermissionDenied):
            create_notice(member, self.workspace, self.lease.id, notice_date=timezone.localdate(), effective_date=timezone.localdate(), notice_type=LeaseNotice.TYPE_OTHER, reason="No permission")
