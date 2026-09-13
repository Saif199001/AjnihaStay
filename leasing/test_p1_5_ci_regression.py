from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseLifecycleEvent
from leasing.models import Lease
from leasing.termination_service import terminate_lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class P15CiRegressionTests(TestCase):
    """Small independent P1.5 smoke suite used to validate a fresh CI run."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="p15-ci-owner@example.com", password="pass"
        )
        self.manager = User.objects.create_user(
            email="p15-ci-manager@example.com", password="pass"
        )
        self.workspace = Workspace.objects.create(
            name="P15 CI Workspace", slug="p15-ci-workspace", owner=self.owner
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner", is_active=True
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.manager, role="manager", is_active=True
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P15 CI Property",
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
            full_name="P15 CI Tenant",
            phone="9999999998",
            email="p15-ci-tenant@example.com",
            permanent_address="Lucknow, Uttar Pradesh",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31),
            next_due_date=date(2026, 1, 1),
            is_active=True,
        )

    def test_fresh_ci_lease_lifecycle_smoke(self):
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
        lease = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE
        )
        lease = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE
        )
        lease = terminate_lease(
            self.manager,
            self.workspace,
            lease.id,
            reason="P1.5 CI regression smoke",
        )

        self.assertEqual(lease.status, Lease.STATUS_TERMINATED)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_TERMINATED
            ).count(),
            1,
        )
