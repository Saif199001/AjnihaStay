from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease, update_lease
from leasing.models import Lease
from leasing.termination_service import terminate_lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseServiceHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="p13-hard-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="p13-hard-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="P13 Hardening", slug="p13-hardening", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="P13 Property",
            property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001",
        )
        self.unit = Unit.objects.create(property=self.property, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="P13 Tenant",
            phone="9999999999", email="p13-hard-tenant@example.com", permanent_address="Lucknow, Uttar Pradesh",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant, unit=self.unit, rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True,
        )

    def data(self, **overrides):
        value = {
            "occupancy": self.occupancy, "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31), "rent_amount": Decimal("12000.00"),
            "security_deposit": Decimal("24000.00"),
        }
        value.update(overrides)
        return value

    def test_create_rejects_occupancy_id_from_other_workspace(self):
        other_owner = User.objects.create_user(email="p13-other-owner@example.com", password="pass")
        other_workspace = Workspace.objects.create(name="Other", slug="p13-other", owner=other_owner)
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner", is_active=True)
        with self.assertRaises(ValidationError):
            create_lease(other_owner, other_workspace, self.data())

    def test_update_cannot_change_lifecycle_or_audit_fields(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        for field, value in (("status", Lease.STATUS_ACTIVE), ("created_by", self.owner), ("updated_by", self.owner), ("activated_at", None)):
            with self.assertRaises(ValidationError):
                update_lease(self.manager, self.workspace, lease.id, {field: value})

    def test_update_rejects_unknown_fields(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        with self.assertRaises(ValidationError):
            update_lease(self.manager, self.workspace, lease.id, {"occupancy_id": self.occupancy.id})

    def test_update_rejects_non_manager_member(self):
        member = User.objects.create_user(email="p13-basic-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        lease = create_lease(self.manager, self.workspace, self.data())
        with self.assertRaises(PermissionDenied):
            update_lease(member, self.workspace, lease.id, {"agreement_number": "NOPE"})

    def test_update_revalidates_date_order(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        with self.assertRaises(ValidationError):
            update_lease(self.manager, self.workspace, lease.id, {"end_date": date(2025, 12, 31)})

    def test_update_preserves_occupancy_and_workspace(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        original_occupancy = lease.occupancy_id
        update_lease(self.manager, self.workspace, lease.id, {"terms": {"pets": False}})
        lease.refresh_from_db()
        self.assertEqual(lease.occupancy_id, original_occupancy)
        self.assertEqual(lease.workspace_id, self.workspace.id)

    def test_lifecycle_terminal_state_is_irreversible(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

        # Terminal lifecycle changes are owned by dedicated services, not the
        # generic transition boundary. Once terminated, the terminal state is
        # irreversible and cannot be changed to expired through that boundary.
        terminate_lease(
            self.manager,
            self.workspace,
            lease.id,
            reason="P1.3 hardening test",
            effective_date=date.today(),
        )
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_TERMINATED)

        with self.assertRaises(ValidationError):
            transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_EXPIRED)

    def test_lifecycle_requires_manager_level_permission(self):
        member = User.objects.create_user(email="p13-basic-transition@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        lease = create_lease(self.manager, self.workspace, self.data())
        with self.assertRaises(PermissionDenied):
            transition_lease(member, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)

    def test_transition_rejects_invalid_target_status(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        with self.assertRaises(ValidationError):
            transition_lease(self.manager, self.workspace, lease.id, "bogus")

    def test_database_unique_occupancy_contract_remains_enforced(self):
        Lease.objects.create(
            workspace=self.workspace, occupancy=self.occupancy,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            rent_amount=Decimal("12000.00"), security_deposit=Decimal("24000.00"), created_by=self.manager,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lease.objects.create(
                    workspace=self.workspace, occupancy=self.occupancy,
                    start_date=date(2027, 1, 1), end_date=date(2027, 12, 31),
                    rent_amount=Decimal("12000.00"), security_deposit=Decimal("24000.00"), created_by=self.manager,
                )

    def test_p1_3_does_not_create_or_mutate_financial_core_records(self):
        lease = create_lease(self.manager, self.workspace, self.data())
        self.assertEqual(lease.rent_amount, Decimal("12000.00"))
        self.assertEqual(lease.security_deposit, Decimal("24000.00"))
        self.assertFalse(hasattr(lease, "invoice"))
