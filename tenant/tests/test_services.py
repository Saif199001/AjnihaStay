from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.services import create_property
from tenant.services import create_charge, create_occupancy, create_tenant, get_charges, get_tenants
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member, archive_workspace


class TenantServiceAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "tenant-service-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Service Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "tenant-service-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Manager Workspace",
        )
        self.viewer = create_user_account(
            "tenant-service-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Viewer Workspace",
        )
        owner_membership = self.owner.workspace_memberships.get()
        add_member(self.workspace, owner_membership, self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, owner_membership, self.viewer.email, Membership.ROLE_VIEWER)

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Tenant Service Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )
        self.unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )

    def tenant_data(self):
        return {
            "full_name": "Test Tenant",
            "phone": "9876543210",
            "permanent_address": "Test Address",
        }

    def occupancy_data(self, tenant):
        return {
            "tenant": tenant.pk,
            "unit": self.unit.pk,
            "rent": Decimal("10000"),
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": date(2026, 10, 1),
            "check_out_date": None,
            "next_due_date": date(2026, 11, 1),
            "security_deposit": Decimal("10000"),
            "deposit_paid": False,
        }

    def test_viewer_cannot_create_tenant_through_service(self):
        with self.assertRaises(PermissionDenied):
            create_tenant(self.viewer, self.workspace, self.tenant_data(), MultiValueDict())

    def test_viewer_cannot_create_occupancy_through_service(self):
        tenant = create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        with self.assertRaises(PermissionDenied):
            create_occupancy(self.viewer, self.workspace, self.occupancy_data(tenant))

    def test_manager_can_create_tenant_through_service(self):
        tenant = create_tenant(
            self.manager,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        self.assertEqual(tenant.owner_id, self.manager.pk)
        self.assertEqual(tenant.workspace_id, self.workspace.pk)

    def test_manager_can_create_occupancy_through_service(self):
        tenant = create_tenant(
            self.manager,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        occupancy = create_occupancy(
            self.manager,
            self.workspace,
            self.occupancy_data(tenant),
        )

        self.assertEqual(occupancy.tenant_id, tenant.pk)
        self.assertEqual(occupancy.unit_id, self.unit.pk)
        self.assertEqual(occupancy.allotted_by_id, self.manager.pk)

    def test_archived_workspace_rejects_tenant_mutation_and_reads(self):
        tenant = create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )
        archive_workspace(self.workspace, self.owner.workspace_memberships.get())

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_tenant(self.owner, self.workspace, self.tenant_data(), MultiValueDict())

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(tenant))

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_charge(
                self.owner,
                self.workspace,
                {
                    "occupancy": occupancy.pk,
                    "charge_type": "food",
                    "amount": Decimal("100"),
                    "charge_date": date(2026, 10, 1),
                },
            )

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            get_tenants(self.workspace)

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            get_charges(occupancy.pk, self.workspace)
