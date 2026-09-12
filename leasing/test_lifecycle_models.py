from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from leasing.lifecycle_models import LeaseLifecycleEvent, LeaseNotice, LeaseRenewal
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseLifecycleModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="p15-owner@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="P15 Workspace", slug="p15-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        property_obj = Property.objects.create(owner=self.owner, workspace=self.workspace, name="P15 Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=property_obj, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="P15 Tenant", phone="9999999999", email="p15-tenant@example.com", permanent_address="Lucknow, Uttar Pradesh")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True)
        self.lease = Lease.objects.create(workspace=self.workspace, occupancy=occupancy, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), rent_amount=Decimal("12000.00"), security_deposit=Decimal("24000.00"), created_by=self.owner)

    def test_field_names_and_indexes_are_under_postgresql_identifier_limit(self):
        for model in (LeaseLifecycleEvent, LeaseNotice, LeaseRenewal):
            for field in model._meta.fields:
                self.assertLess(len(field.name), 30)
            for index in model._meta.indexes:
                self.assertLess(len(index.name), 30)
            for constraint in model._meta.constraints:
                self.assertLess(len(constraint.name), 30)

    def test_related_names_are_explicit_and_distinct(self):
        self.assertEqual(LeaseLifecycleEvent._meta.get_field("lease").remote_field.related_name, "lifecycle_events")
        self.assertEqual(LeaseLifecycleEvent._meta.get_field("workspace").remote_field.related_name, "lease_lifecycle_events")
        self.assertEqual(LeaseNotice._meta.get_field("lease").remote_field.related_name, "notices")
        self.assertEqual(LeaseNotice._meta.get_field("workspace").remote_field.related_name, "lease_notices")
        self.assertEqual(LeaseRenewal._meta.get_field("source_lease").remote_field.related_name, "renewals")
        self.assertEqual(LeaseRenewal._meta.get_field("workspace").remote_field.related_name, "lease_renewals")

    def test_lifecycle_event_preserves_workspace_and_actor_contract(self):
        event = LeaseLifecycleEvent.objects.create(workspace=self.workspace, lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_ACTIVATED, occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc), effective_date=date(2026, 1, 1), actor=self.owner, metadata={"source": "p1.5"})
        self.assertEqual(event.lease_id, self.lease.id)
        self.assertEqual(event.workspace_id, self.workspace.id)
        self.assertEqual(event.actor_id, self.owner.id)

    def test_lifecycle_event_is_immutable(self):
        event = LeaseLifecycleEvent.objects.create(workspace=self.workspace, lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_CREATED, occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc), actor=self.owner)
        event.event_type = LeaseLifecycleEvent.EVENT_TERMINATED
        with self.assertRaises(ValidationError):
            event.save()

    def test_lifecycle_event_rejects_cross_workspace_lease(self):
        other_owner = User.objects.create_user(email="p15-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="P15 Other", slug="p15-other-workspace", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            LeaseLifecycleEvent.objects.create(workspace=other_workspace, lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_NOTICE, occurred_at=datetime(2026, 2, 1, tzinfo=timezone.utc), actor=other_owner)

    def test_notice_requires_reason_and_valid_dates(self):
        notice = LeaseNotice.objects.create(workspace=self.workspace, lease=self.lease, notice_date=date(2026, 6, 1), effective_date=date(2026, 7, 1), notice_type=LeaseNotice.TYPE_TERMINATION, reason="Contractual termination", created_by=self.owner)
        self.assertEqual(notice.status, LeaseNotice.STATUS_DRAFT)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LeaseNotice.objects.create(workspace=self.workspace, lease=self.lease, notice_date=date(2026, 6, 2), effective_date=date(2026, 6, 1), notice_type=LeaseNotice.TYPE_TERMINATION, reason="Invalid date", created_by=self.owner)
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.create(workspace=self.workspace, lease=self.lease, notice_date=date(2026, 6, 1), effective_date=date(2026, 7, 1), notice_type=LeaseNotice.TYPE_TERMINATION, reason="   ", created_by=self.owner)

    def test_renewal_preserves_source_and_contract_snapshot(self):
        renewal = LeaseRenewal.objects.create(workspace=self.workspace, source_lease=self.lease, renewal_number=1, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), rent_amount=Decimal("13500.00"), security_deposit=Decimal("27000.00"), created_by=self.owner)
        self.assertEqual(renewal.source_lease_id, self.lease.id)
        self.assertEqual(renewal.renewal_number, 1)
        self.assertEqual(renewal.rent_amount, Decimal("13500.00"))
        self.assertEqual(renewal.status, LeaseRenewal.STATUS_DRAFT)
        self.assertEqual(self.lease.rent_amount, Decimal("12000.00"))

    def test_renewal_number_is_unique_per_source_lease(self):
        LeaseRenewal.objects.create(workspace=self.workspace, source_lease=self.lease, renewal_number=1, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), rent_amount=Decimal("13500.00"), created_by=self.owner)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LeaseRenewal.objects.create(workspace=self.workspace, source_lease=self.lease, renewal_number=1, start_date=date(2028, 1, 1), end_date=date(2028, 12, 31), rent_amount=Decimal("14500.00"), created_by=self.owner)

    def test_renewal_rejects_cross_workspace_source(self):
        other_owner = User.objects.create_user(email="p15-renew-other@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="P15 Renewal Other", slug="p15-renew-other", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            LeaseRenewal.objects.create(workspace=other_workspace, source_lease=self.lease, renewal_number=1, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), rent_amount=Decimal("13500.00"), created_by=other_owner)

    def test_confirmed_renewal_is_immutable(self):
        renewal = LeaseRenewal.objects.create(workspace=self.workspace, source_lease=self.lease, renewal_number=1, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), rent_amount=Decimal("13500.00"), created_by=self.owner)
        renewal.status = LeaseRenewal.STATUS_CONFIRMED
        renewal.save()
        renewal.rent_amount = Decimal("14000.00")
        with self.assertRaises(ValidationError):
            renewal.save()
