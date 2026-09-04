from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Tenant, Occupancy


class WorkspaceRelationshipIntegrityTests(TestCase):
    def setUp(self):
        password = "StrongPass123!"
        self.owner = User.objects.create_user("integrity-owner@example.com", password)
        self.other = User.objects.create_user("integrity-other@example.com", password)
        self.workspace = Workspace.objects.create(
            name="Integrity Workspace", slug="integrity-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Integrity Workspace", slug="other-integrity-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Integrity Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="101",
            rent=Decimal("10000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Integrity Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )

    def test_tenant_rejects_owner_from_another_workspace(self):
        with self.assertRaises(ValidationError):
            Tenant.objects.create(
                owner=self.other,
                workspace=self.workspace,
                full_name="Cross Workspace Tenant",
                phone="8888888888",
                permanent_address="Delhi",
            )

    def test_tenant_rejects_inactive_workspace_owner(self):
        membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            Tenant.objects.create(
                owner=self.owner,
                workspace=self.workspace,
                full_name="Inactive Owner Tenant",
                phone="7777777777",
                permanent_address="Delhi",
            )

    def test_occupancy_rejects_allotted_by_user_from_another_workspace(self):
        with self.assertRaises(ValidationError):
            Occupancy.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                allotted_by=self.other,
                rent=Decimal("10000.00"),
                check_in_date=date(2026, 9, 1),
                next_due_date=date(2026, 10, 1),
            )

    def test_occupancy_rejects_inactive_allotted_by_user(self):
        membership = Membership.objects.get(workspace=self.workspace, user=self.owner)
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            Occupancy.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                allotted_by=self.owner,
                rent=Decimal("10000.00"),
                check_in_date=date(2026, 9, 1),
                next_due_date=date(2026, 10, 1),
            )
