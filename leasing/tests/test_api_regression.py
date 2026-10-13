from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIClient

from accounts.services import create_user_account
from leasing.lifecycle_models import LeaseLifecycleEvent
from leasing.models import Lease
from properties.services import create_property
from tenant.services import create_occupancy, create_tenant
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class LeaseCreationAPIRegressionTests(TestCase):
    """HTTP-level regression coverage for canonical Lease creation boundaries."""

    def setUp(self):
        self.client = APIClient()
        self.owner = create_user_account(
            "lease-api-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()
        owner_membership = self.owner.workspace_memberships.get()

        self.manager = create_user_account(
            "lease-api-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Manager Workspace",
        )
        self.viewer = create_user_account(
            "lease-api-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Viewer Workspace",
        )
        add_member(
            self.workspace,
            owner_membership,
            self.manager.email,
            Membership.ROLE_MANAGER,
        )
        add_member(
            self.workspace,
            owner_membership,
            self.viewer.email,
            Membership.ROLE_VIEWER,
        )

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Lease API Property",
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
                "unit_number": "LEASE-101",
                "unit_type": "room",
                "rent": Decimal("10000.00"),
                "capacity": 1,
                "description": "",
            },
        )
        self.occupancy = self.create_occupancy_record()

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        active_workspace = workspace or self.workspace
        return {"HTTP_X_WORKSPACE_ID": str(active_workspace.pk)}

    def create_occupancy_record(self, owner=None, workspace=None, unit=None):
        owner = owner or self.owner
        workspace = workspace or self.workspace
        unit = unit or self.unit
        tenant = create_tenant(
            owner,
            workspace,
            {
                "full_name": "Lease API Tenant",
                "phone": "9876543210",
                "permanent_address": "Test Address",
            },
            MultiValueDict(),
        )
        return create_occupancy(
            owner,
            workspace,
            {
                "tenant": tenant.pk,
                "unit": unit.pk,
                "rent": Decimal("10000.00"),
                "billing_type": "advance",
                "billing_cycle": "monthly",
                "check_in_date": date(2026, 10, 1),
                "check_out_date": None,
                "next_due_date": date(2026, 11, 1),
                "security_deposit": Decimal("10000.00"),
                "deposit_paid": False,
            },
        )

    def lease_payload(self, occupancy=None, **overrides):
        payload = {
            "occupancy": (occupancy or self.occupancy).pk,
            "agreement_number": "LEASE-API-001",
            "start_date": "2026-10-01",
            "end_date": "2027-09-30",
            "rent_amount": "10000.00",
            "security_deposit": "10000.00",
            "notice_period_days": 30,
            "terms": {"maintenance": "owner"},
            "agreement_reference": "contract-reference",
        }
        payload.update(overrides)
        return payload

    def create_lease_through_api(self, user=None, **payload_overrides):
        headers = self.authenticate(user or self.manager)
        return self.client.post(
            "/api/leases/create/",
            self.lease_payload(**payload_overrides),
            format="json",
            **headers,
        )

    def test_create_requires_authentication(self):
        response = self.client.post(
            "/api/leases/create/",
            self.lease_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_viewer_cannot_create_lease(self):
        response = self.create_lease_through_api(user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Lease.objects.filter(occupancy=self.occupancy).exists())

    def test_manager_creates_draft_lease_through_canonical_api(self):
        response = self.create_lease_through_api()

        self.assertEqual(response.status_code, 201, response.data)
        lease = Lease.objects.get(occupancy=self.occupancy)
        self.assertEqual(response.data["data"]["id"], lease.pk)
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)
        self.assertEqual(lease.workspace_id, self.workspace.pk)
        self.assertEqual(lease.created_by_id, self.manager.pk)
        self.assertTrue(
            LeaseLifecycleEvent.objects.filter(
                lease=lease,
                event_type=LeaseLifecycleEvent.EVENT_CREATED,
            ).exists()
        )

    def test_duplicate_occupancy_returns_controlled_http_400(self):
        first = self.create_lease_through_api()
        self.assertEqual(first.status_code, 201, first.data)

        second = self.create_lease_through_api(
            agreement_number="LEASE-API-DUPLICATE"
        )
        self.assertEqual(second.status_code, 400, second.data)
        self.assertEqual(
            second.data["error"],
            "A lease already exists for this occupancy",
        )
        self.assertEqual(Lease.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_invalid_lease_payload_returns_http_400(self):
        response = self.create_lease_through_api(
            start_date="2027-01-01",
            end_date="2026-12-31",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Lease.objects.filter(occupancy=self.occupancy).count(), 0)

    def test_occupancy_from_another_workspace_is_rejected(self):
        outsider = create_user_account(
            "lease-api-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Other Workspace",
        )
        other_workspace = outsider.owned_workspaces.get()
        other_property = create_property(
            outsider,
            other_workspace,
            {
                "owner": outsider,
                "name": "Other Lease API Property",
                "property_type": "pg",
                "description": "",
                "address": "Other Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226002",
                "amenities": [],
            },
            MultiValueDict(),
        )
        other_unit = create_unit(
            outsider,
            other_workspace,
            {
                "property": other_property,
                "unit_number": "OTHER-101",
                "unit_type": "room",
                "rent": Decimal("9000.00"),
                "capacity": 1,
                "description": "",
            },
        )
        other_occupancy = self.create_occupancy_record(
            owner=outsider,
            workspace=other_workspace,
            unit=other_unit,
        )

        response = self.create_lease_through_api(occupancy=other_occupancy)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["error"], "Occupancy not found")
        self.assertFalse(Lease.objects.filter(occupancy=other_occupancy).exists())

    def test_update_and_valid_lifecycle_transitions_use_api_contract(self):
        created = self.create_lease_through_api()
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)

        updated = self.client.post(
            f"/api/leases/{lease_id}/update/",
            {"agreement_number": "LEASE-API-UPDATED"},
            format="json",
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["data"]["agreement_number"], "LEASE-API-UPDATED")

        pending = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_PENDING_SIGNATURE},
            format="json",
            **headers,
        )
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(pending.data["data"]["status"], Lease.STATUS_PENDING_SIGNATURE)

        active = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_ACTIVE},
            format="json",
            **headers,
        )
        self.assertEqual(active.status_code, 200, active.data)
        self.assertEqual(active.data["data"]["status"], Lease.STATUS_ACTIVE)

        invalid_retry = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_DRAFT},
            format="json",
            **headers,
        )
        self.assertEqual(invalid_retry.status_code, 400, invalid_retry.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)
        self.assertIsNotNone(lease.activated_at)

    def test_cross_workspace_header_is_rejected(self):
        outsider = create_user_account(
            "lease-api-header-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Header Workspace",
        )
        response = self.client.post(
            "/api/leases/create/",
            self.lease_payload(),
            format="json",
            **self.authenticate(self.owner, outsider.owned_workspaces.get()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Lease.objects.filter(occupancy=self.occupancy).exists())
