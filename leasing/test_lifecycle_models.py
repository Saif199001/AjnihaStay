from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from leasing.lifecycle_models import LeaseLifecycleEvent, LeaseNotice
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseLifecycleModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p15-owner@example.com", password="pass"
        )
        self.workspace = Workspace.objects.create(
            name="P15 Workspace", slug="p15-workspace", owner=self.owner
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role="owner",
            is_active=True,
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P15 Property",
            property_type="flat",
            address="Address",
            city="Lucknow",
            state="UP",
            pincode="226001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="flat",
            unit_number="101",
            rent=Decimal("12000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="P15 Tenant",
            phone="9999999999",
            email="p15-tenant@example.com",
            permanent_address="Lucknow, Uttar Pradesh",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31),
            next_due_date=date(2026, 1, 1),
            is_active=True,
        )
        self.lease = Lease.objects.create(
            workspace=self.workspace,
            occupancy=occupancy,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent_amount=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            created_by=self.owner,
        )

    def test_field_names_and_indexes_are_under_postgresql_identifier_limit(self):
        for model in (LeaseLifecycleEvent, LeaseNotice):
            for field in model._meta.fields:
                self.assertLess(len(field.name), 30)
            for index in model._meta.indexes:
                self.assertLess(len(index.name), 30)

    def test_related_names_are_explicit_and_distinct(self):
        self.assertEqual(LeaseLifecycleEvent._meta.get_field("lease").remote_field.related_name, "lifecycle_events")
        self.assertEqual(LeaseLifecycleEvent._meta.get_field("workspace").remote_field.related_name, "lease_lifecycle_events")
        self.assertEqual(LeaseNotice._meta.get_field("lease").remote_field.related_name, "notices")
        self.assertEqual(LeaseNotice._meta.get_field("workspace").remote_field.related_name, "lease_notices")

    def test_lifecycle_event_preserves_workspace_and_actor_contract(self):
        event = LeaseLifecycleEvent.objects.create(
            workspace=self.workspace,
            lease=self.lease,
            event_type=LeaseLifecycleEvent.EVENT_ACTIVATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            effective_date=date(2026, 1, 1),
            actor=self.owner,
            metadata={"source": "p1.5"},
        )
        self.assertEqual(event.lease_id, self.lease.id)
        self.assertEqual(event.workspace_id, self.workspace.id)
        self.assertEqual(event.actor_id, self.owner.id)

    def test_lifecycle_event_is_immutable(self):
        event = LeaseLifecycleEvent.objects.create(
            workspace=self.workspace,
            lease=self.lease,
            event_type=LeaseLifecycleEvent.EVENT_CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            actor=self.owner,
        )
        event.event_type = LeaseLifecycleEvent.EVENT_TERMINATED
        with self.assertRaises(ValidationError):
            event.save()

    def test_lifecycle_event_rejects_cross_workspace_lease(self):
        other_owner = User.objects.create_user(
            email="p15-other@example.com", password="pass"
        )
        other_workspace = Workspace.objects.create(
            name="P15 Other", slug="p15-other-workspace", owner=other_owner
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role="owner",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            LeaseLifecycleEvent.objects.create(
                workspace=other_workspace,
                lease=self.lease,
                event_type=LeaseLifecycleEvent.EVENT_NOTICE,
                occurred_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                actor=other_owner,
            )

    def test_notice_requires_reason_and_valid_dates(self):
        notice = LeaseNotice.objects.create(
            workspace=self.workspace,
            lease=self.lease,
            notice_date=date(2026, 6, 1),
            effective_date=date(2026, 7, 1),
            notice_type=LeaseNotice.TYPE_TERMINATION,
            reason="Contractual termination",
            created_by=self.owner,
        )
        self.assertEqual(notice.status, LeaseNotice.STATUS_DRAFT)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LeaseNotice.objects.create(
                    workspace=self.workspace,
                    lease=self.lease,
                    notice_date=date(2026, 6, 2),
                    effective_date=date(2026, 6, 1),
                    notice_type=LeaseNotice.TYPE_TERMINATION,
                    reason="Invalid date",
                    created_by=self.owner,
                )
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.create(
                workspace=self.workspace,
                lease=self.lease,
                notice_date=date(2026, 6, 1),
                effective_date=date(2026, 7, 1),
                notice_type=LeaseNotice.TYPE_TERMINATION,
                reason="   ",
                created_by=self.owner,
            )
