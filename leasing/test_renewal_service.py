from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import User
from leasing.lifecycle_models import LeaseRenewal
from leasing.models import Lease
from leasing.renewal_service import cancel_renewal, confirm_renewal, create_renewal
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseRenewalServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="renew-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="renew-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="Renewal Workspace", slug="renewal-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        property_obj = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Renewal Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=property_obj, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Renewal Tenant", phone="9999999999", email="renew-tenant@example.com", permanent_address="Lucknow, Uttar Pradesh")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True)
        self.lease = Lease.objects.create(workspace=self.workspace, occupancy=occupancy, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), rent_amount=Decimal("12000.00"), security_deposit=Decimal("24000.00"), created_by=self.owner, status=Lease.STATUS_ACTIVE)

    def _data(self, **overrides):
        data = {"start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31)}
        data.update(overrides)
        return data

    def test_create_renewal_uses_source_snapshot_and_auto_number(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        self.assertEqual(renewal.renewal_number, 1)
        self.assertEqual(renewal.rent_amount, Decimal("12000.00"))
        self.assertEqual(renewal.security_deposit, Decimal("24000.00"))
        self.assertEqual(renewal.terms, self.lease.terms)
        self.assertEqual(renewal.status, LeaseRenewal.STATUS_DRAFT)
        self.assertEqual(self.lease.rent_amount, Decimal("12000.00"))

    def test_create_renewal_increments_number_per_source(self):
        create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data(start_date=date(2028, 1, 1), end_date=date(2028, 12, 31)))
        self.assertEqual(renewal.renewal_number, 2)

    def test_create_renewal_rejects_overlap_with_source_or_prior_renewal(self):
        with self.assertRaises(ValidationError):
            create_renewal(self.manager, self.workspace, self.lease.id, self._data(start_date=date(2026, 12, 1), end_date=date(2027, 11, 30)))
        create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        with self.assertRaises(ValidationError):
            create_renewal(self.manager, self.workspace, self.lease.id, self._data(start_date=date(2027, 6, 1), end_date=date(2028, 5, 31)))

    def test_create_renewal_rejects_invalid_source_state(self):
        self.lease.status = Lease.STATUS_DRAFT
        self.lease.save()
        with self.assertRaises(ValidationError):
            create_renewal(self.manager, self.workspace, self.lease.id, self._data())

    def test_create_renewal_requires_manager_permission(self):
        member = User.objects.create_user(email="renew-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        with self.assertRaises(PermissionDenied):
            create_renewal(member, self.workspace, self.lease.id, self._data())

    def test_create_renewal_rejects_cross_workspace_source(self):
        other_owner = User.objects.create_user(email="renew-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="Other Renewal", slug="other-renewal", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            create_renewal(other_owner, other_workspace, self.lease.id, self._data())

    def test_confirm_renewal_sets_confirmed_at_and_is_idempotent(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        confirmed = confirm_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(confirmed.status, LeaseRenewal.STATUS_CONFIRMED)
        self.assertIsNotNone(confirmed.confirmed_at)
        again = confirm_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(again.id, renewal.id)
        self.assertEqual(again.status, LeaseRenewal.STATUS_CONFIRMED)

    def test_confirm_renewal_rejects_cancelled(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        cancel_renewal(self.manager, self.workspace, renewal.id)
        with self.assertRaises(ValidationError):
            confirm_renewal(self.manager, self.workspace, renewal.id)

    def test_confirm_renewal_rejects_invalid_source_state(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        self.lease.status = Lease.STATUS_TERMINATED
        self.lease.save()
        with self.assertRaises(ValidationError):
            confirm_renewal(self.manager, self.workspace, renewal.id)

    def test_cancel_renewal_sets_cancelled_at_and_is_idempotent(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        cancelled = cancel_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(cancelled.status, LeaseRenewal.STATUS_CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        again = cancel_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(again.id, renewal.id)
        self.assertEqual(again.status, LeaseRenewal.STATUS_CANCELLED)

    def test_cancel_renewal_rejects_confirmed(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        confirm_renewal(self.manager, self.workspace, renewal.id)
        with self.assertRaises(ValidationError):
            cancel_renewal(self.manager, self.workspace, renewal.id)

    def test_renewal_mutations_require_manager_permission(self):
        member = User.objects.create_user(email="renew-member-2@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self._data())
        with self.assertRaises(PermissionDenied):
            confirm_renewal(member, self.workspace, renewal.id)
        with self.assertRaises(PermissionDenied):
            cancel_renewal(member, self.workspace, renewal.id)
