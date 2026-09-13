from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease, update_lease
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="p13-owner@example.com",
            password="pass",
        )
        self.manager = User.objects.create_user(
            email="p13-manager@example.com",
            password="pass",
        )
        self.workspace = Workspace.objects.create(
            name="P13 Workspace",
            slug="p13-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role="owner",
            is_active=True,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role="manager",
            is_active=True,
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P13 Property",
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
            full_name="P13 Tenant",
            phone="9999999999",
            email="p13-tenant@example.com",
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

    def _data(self, **overrides):
        data = {
            "occupancy": self.occupancy,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "rent_amount": Decimal("12000.00"),
            "security_deposit": Decimal("24000.00"),
        }
        data.update(overrides)
        return data

    def test_create_lease_uses_canonical_defaults_and_draft_status(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)
        self.assertEqual(lease.rent_amount, Decimal("12000.00"))
        self.assertEqual(lease.security_deposit, Decimal("24000.00"))
        self.assertEqual(lease.created_by_id, self.manager.id)

    def test_create_lease_records_immutable_created_event(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CREATED)
        self.assertEqual(event.event_type, LeaseLifecycleEvent.EVENT_CREATED)
        self.assertEqual(event.actor_id, self.manager.id)
        self.assertEqual(event.effective_date, lease.start_date)
        self.assertEqual(event.metadata["status"], Lease.STATUS_DRAFT)
        with self.assertRaises(ValidationError):
            event.metadata = {"tampered": True}
            event.save()

    def test_create_rejects_cross_workspace_occupancy(self):
        other_owner = User.objects.create_user(
            email="p13-other@example.com",
            password="pass",
        )
        other_workspace = Workspace.objects.create(
            name="Other P13",
            slug="other-p13-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role="owner",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            create_lease(other_owner, other_workspace, self._data())

    def test_create_requires_manager_level_permission(self):
        member = User.objects.create_user(
            email="p13-member@example.com",
            password="pass",
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=member,
            role="member",
            is_active=True,
        )
        with self.assertRaises(PermissionDenied):
            create_lease(member, self.workspace, self._data())

    def test_create_rejects_non_draft_status(self):
        with self.assertRaises(ValidationError):
            create_lease(
                self.manager,
                self.workspace,
                self._data(status=Lease.STATUS_ACTIVE),
            )

    def test_update_allows_contract_fields_and_records_actor(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        updated = update_lease(
            self.manager,
            self.workspace,
            lease.id,
            {
                "agreement_number": "LEASE-P13-001",
                "rent_amount": Decimal("12500.00"),
                "notice_period_days": 30,
            },
        )
        self.assertEqual(updated.agreement_number, "LEASE-P13-001")
        self.assertEqual(updated.rent_amount, Decimal("12500.00"))
        self.assertEqual(updated.notice_period_days, 30)
        self.assertEqual(updated.updated_by_id, self.manager.id)

    def test_update_rejects_contract_changes_after_activation(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        lease = transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)
        self.assertEqual(LeaseContractVersion.objects.filter(lease=lease).count(), 1)
        with self.assertRaises(ValidationError):
            update_lease(
                self.manager,
                self.workspace,
                lease.id,
                {"rent_amount": Decimal("12500.00")},
            )
        lease.refresh_from_db()
        self.assertEqual(lease.rent_amount, Decimal("12000.00"))

    def test_update_rejects_status_occupancy_and_workspace_mutation(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        for field, value in (
            ("status", Lease.STATUS_ACTIVE),
            ("occupancy", self.occupancy),
            ("workspace", self.workspace),
            ("created_by", self.manager),
        ):
            with self.assertRaises(ValidationError):
                update_lease(
                    self.manager,
                    self.workspace,
                    lease.id,
                    {field: value},
                )

    def test_update_rejects_negative_and_over_precision_money(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        with self.assertRaises(ValidationError):
            update_lease(
                self.manager,
                self.workspace,
                lease.id,
                {"rent_amount": Decimal("-1.00")},
            )
        with self.assertRaises(ValidationError):
            update_lease(
                self.manager,
                self.workspace,
                lease.id,
                {"rent_amount": Decimal("1.001")},
            )

    def test_lifecycle_transitions_record_one_canonical_event_each(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_TERMINATED)

        events = LeaseLifecycleEvent.objects.filter(lease=lease).order_by("occurred_at", "id")
        self.assertEqual(events.count(), 4)
        self.assertEqual(
            list(events.values_list("event_type", flat=True)),
            ["created", "pending_signature", "activated", "terminated"],
        )
        terminated = events.get(event_type=LeaseLifecycleEvent.EVENT_TERMINATED)
        self.assertEqual(terminated.actor_id, self.manager.id)
        self.assertEqual(terminated.metadata["from_status"], Lease.STATUS_ACTIVE)
        self.assertEqual(terminated.metadata["to_status"], Lease.STATUS_TERMINATED)

    def test_same_status_transition_does_not_duplicate_event(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease,
                event_key=LeaseLifecycleEvent.EVENT_PENDING_SIGNATURE,
            ).count(),
            1,
        )

    def test_lifecycle_supports_cancellation_before_activation(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        lease = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_CANCELLED
        )
        self.assertEqual(lease.status, Lease.STATUS_CANCELLED)
        self.assertIsNotNone(lease.cancelled_at)
        event = LeaseLifecycleEvent.objects.get(lease=lease, event_type=LeaseLifecycleEvent.EVENT_CANCELLED)
        self.assertEqual(event.metadata["from_status"], Lease.STATUS_DRAFT)

    def test_invalid_lifecycle_transition_is_rejected(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        with self.assertRaises(ValidationError):
            transition_lease(
                self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE
            )

    def test_terminal_lifecycle_state_cannot_change(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        lease = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_CANCELLED
        )
        with self.assertRaises(ValidationError):
            transition_lease(
                self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE
            )

    def test_same_status_transition_is_idempotent_noop(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        first = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE
        )
        second = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.status, Lease.STATUS_PENDING_SIGNATURE)

    def test_transition_rejects_cross_workspace_lease(self):
        lease = create_lease(self.manager, self.workspace, self._data())
        other_owner = User.objects.create_user(
            email="p13-cross@example.com",
            password="pass",
        )
        other_workspace = Workspace.objects.create(
            name="Cross P13",
            slug="cross-p13-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role="owner",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            transition_lease(
                other_owner,
                other_workspace,
                lease.id,
                Lease.STATUS_PENDING_SIGNATURE,
            )
