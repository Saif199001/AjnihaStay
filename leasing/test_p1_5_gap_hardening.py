from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent, LeaseNotice
from leasing.models import Lease
from leasing.notice_service import create_notice, transition_notice
from leasing.renewal_service import cancel_renewal, confirm_renewal, create_renewal
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class P15GapHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="gap-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="gap-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="Gap Workspace", slug="gap-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        prop = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Gap Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=prop, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Gap Tenant", phone="9999999999", email="gap-tenant@example.com", permanent_address="Lucknow")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True)
        lease = create_lease(self.manager, self.workspace, {"occupancy": occupancy, "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "rent_amount": Decimal("12000.00"), "security_deposit": Decimal("24000.00")})
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.lease = transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def _renewal(self):
        return create_renewal(
            self.manager,
            self.workspace,
            self.lease.id,
            {"start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31), "rent_amount": Decimal("13500.00")},
        )

    def _notice(self):
        return create_notice(
            self.manager,
            self.workspace,
            self.lease.id,
            notice_date=timezone.localdate(),
            effective_date=timezone.localdate(),
            notice_type=LeaseNotice.TYPE_TERMINATION,
            reason="Gap hardening notice",
        )

    def test_notice_direct_create_is_blocked(self):
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.create(
                workspace=self.workspace,
                lease=self.lease,
                notice_date=timezone.localdate(),
                effective_date=timezone.localdate(),
                notice_type=LeaseNotice.TYPE_TERMINATION,
                reason="Bypass",
                created_by=self.manager,
            )

    def test_notice_direct_status_save_and_bulk_update_are_blocked(self):
        notice = self._notice()
        notice.status = LeaseNotice.STATUS_ISSUED
        with self.assertRaises(ValidationError):
            notice.save()
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.filter(pk=notice.pk).update(status=LeaseNotice.STATUS_ISSUED)
        notice.refresh_from_db()
        self.assertEqual(notice.status, LeaseNotice.STATUS_DRAFT)
        transition_notice(self.manager, self.workspace, notice.id, LeaseNotice.STATUS_ISSUED)
        notice.refresh_from_db()
        self.assertEqual(notice.status, LeaseNotice.STATUS_ISSUED)

    def test_confirmed_renewal_bulk_update_is_blocked(self):
        renewal = self._renewal()
        confirm_renewal(self.manager, self.workspace, renewal.id)
        with self.assertRaises(ValidationError):
            LeaseRenewal.objects.filter(pk=renewal.pk).update(rent_amount=Decimal("1.00"))

    def test_contract_version_bulk_update_is_blocked(self):
        renewal = self._renewal()
        confirm_renewal(self.manager, self.workspace, renewal.id)
        successor = LeaseContractVersion.objects.get(pk=renewal.successor_version_id)
        with self.assertRaises(ValidationError):
            LeaseContractVersion.objects.filter(pk=successor.pk).update(rent_amount=Decimal("1.00"))

    def test_lifecycle_event_bulk_update_is_blocked(self):
        self._notice()
        event = LeaseLifecycleEvent.objects.get(lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_NOTICE)
        with self.assertRaises(ValidationError):
            LeaseLifecycleEvent.objects.filter(pk=event.pk).update(metadata={"tampered": True})

    def test_renewal_cancellation_records_lifecycle_event_and_is_idempotent(self):
        renewal = self._renewal()
        first = cancel_renewal(self.manager, self.workspace, renewal.id)
        second = cancel_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, LeaseRenewal.STATUS_CANCELLED)
        events = LeaseLifecycleEvent.objects.filter(lease=self.lease, event_key=f"renewal:{renewal.id}:cancelled")
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.event_type, LeaseLifecycleEvent.EVENT_RENEWED)
        self.assertEqual(event.metadata["action"], "cancelled")
