from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from leasing.api import (
    lease_renewal_cancel_api,
    lease_renewal_confirm_api,
    lease_renewal_create_api,
)
from leasing.lease_service import create_lease, transition_lease
from leasing.models import Lease
from leasing.renewal_service import create_renewal
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseP15AdversarialRenewalApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(email="p15-api-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="p15-api-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(
            name="P15 API Workspace", slug="p15-api-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)

        prop = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P15 API Property",
            property_type="flat",
            address="Address",
            city="Lucknow",
            state="UP",
            pincode="226001",
        )
        unit = Unit.objects.create(
            property=prop, unit_type="flat", unit_number="101", rent=Decimal("12000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="P15 API Tenant",
            phone="9999999999",
            email="p15-api-tenant@example.com",
            permanent_address="Lucknow",
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
        lease = create_lease(
            self.manager,
            self.workspace,
            {
                "occupancy": occupancy,
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "rent_amount": Decimal("12000.00"),
                "security_deposit": Decimal("24000.00"),
            },
        )
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.lease = transition_lease(
            self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE
        )

    def auth(self, request, user=None, workspace=None):
        force_authenticate(request, user=user or self.manager)
        request.workspace = workspace or self.workspace
        return request

    def payload(self, **overrides):
        data = {
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "rent_amount": "13500.00",
            "security_deposit": "27000.00",
            "notice_period_days": 30,
            "terms": {"pets": False},
            "agreement_reference": "REN-API-001",
        }
        data.update(overrides)
        return data

    def create_renewal_via_api(self, **overrides):
        request = self.auth(
            self.factory.post(
                f"/api/leases/{self.lease.id}/renewals/create/",
                self.payload(**overrides),
                format="json",
            )
        )
        response = lease_renewal_create_api(request, self.lease.id)
        self.assertEqual(response.status_code, 201)
        return response.data["data"]["id"]

    def test_renewal_create_wrong_workspace_returns_400(self):
        other_owner = User.objects.create_user(email="p15-api-other@example.com", password="pass")
        other = Workspace.objects.create(
            name="Other P15 API", slug="other-p15-api", owner=other_owner
        )
        Membership.objects.create(workspace=other, user=other_owner, role="owner", is_active=True)
        request = self.auth(
            self.factory.post(
                f"/api/leases/{self.lease.id}/renewals/create/",
                self.payload(),
                format="json",
            ),
            other_owner,
            other,
        )
        response = lease_renewal_create_api(request, self.lease.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Lease not found")

    def test_renewal_actions_invalid_ids_return_400(self):
        for view, path, argument in (
            (
                lease_renewal_confirm_api,
                "/api/leases/renewals/999999/confirm/",
                999999,
            ),
            (
                lease_renewal_cancel_api,
                "/api/leases/renewals/999999/cancel/",
                999999,
            ),
        ):
            request = self.auth(self.factory.post(path, {}, format="json"))
            response = view(request, argument)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["error"], "Renewal not found")

    def test_renewal_api_requires_active_manager_membership(self):
        inactive = User.objects.create_user(email="p15-api-inactive@example.com", password="pass")
        Membership.objects.create(
            workspace=self.workspace, user=inactive, role="manager", is_active=False
        )
        request = self.auth(
            self.factory.post(
                f"/api/leases/{self.lease.id}/renewals/create/",
                self.payload(),
                format="json",
            ),
            inactive,
        )
        response = lease_renewal_create_api(request, self.lease.id)
        self.assertEqual(response.status_code, 403)

    def test_renewal_api_unauthenticated_actions_return_401(self):
        renewal_id = self.create_renewal_via_api()
        cases = (
            lease_renewal_confirm_api,
            lease_renewal_cancel_api,
        )
        for view in cases:
            request = self.factory.post("/api/leases/renewals/action/", {}, format="json")
            request.workspace = self.workspace
            response = view(request, renewal_id)
            self.assertEqual(response.status_code, 401)

    def test_renewal_create_rejects_malformed_dates_and_negative_money(self):
        response = lease_renewal_create_api(
            self.auth(
                self.factory.post(
                    f"/api/leases/{self.lease.id}/renewals/create/",
                    self.payload(start_date="not-a-date"),
                    format="json",
                )
            ),
            self.lease.id,
        )
        self.assertEqual(response.status_code, 400)

        response = lease_renewal_create_api(
            self.auth(
                self.factory.post(
                    f"/api/leases/{self.lease.id}/renewals/create/",
                    self.payload(rent_amount="-1.00"),
                    format="json",
                )
            ),
            self.lease.id,
        )
        self.assertEqual(response.status_code, 400)

    def test_renewal_create_rejects_unsupported_fields(self):
        response = lease_renewal_create_api(
            self.auth(
                self.factory.post(
                    f"/api/leases/{self.lease.id}/renewals/create/",
                    self.payload(status=Lease.STATUS_CONFIRMED),
                    format="json",
                )
            ),
            self.lease.id,
        )
        self.assertEqual(response.status_code, 400)

        renewal = create_renewal(
            self.manager,
            self.workspace,
            self.lease.id,
            {"start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31)},
        )
        request = self.auth(
            self.factory.post(
                f"/api/leases/renewals/{renewal.id}/confirm/",
                {"successor_version": 999999},
                format="json",
            )
        )
        response = lease_renewal_confirm_api(request, renewal.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["data"]["status"], Lease.STATUS_CONFIRMED)

    def test_renewal_create_response_contract_exposes_only_expected_mutable_fields(self):
        renewal_id = self.create_renewal_via_api()
        renewal_response = lease_renewal_confirm_api(
            self.auth(
                self.factory.post(
                    f"/api/leases/renewals/{renewal_id}/confirm/", {}, format="json"
                )
            ),
            renewal_id,
        )
        self.assertEqual(renewal_response.status_code, 200)
        data = renewal_response.data["data"]
        for field in ("id", "workspace", "source_lease", "status", "successor_version"):
            self.assertIn(field, data)
        self.assertEqual(data["status"], "confirmed")

    def test_terminal_source_lease_cannot_be_renewed(self):
        from leasing.termination_service import terminate_lease

        terminate_lease(
            self.manager,
            self.workspace,
            self.lease.id,
            reason="P15 API terminal source test",
            effective_date=date(2026, 9, 13),
        )
        request = self.auth(
            self.factory.post(
                f"/api/leases/{self.lease.id}/renewals/create/",
                self.payload(),
                format="json",
            )
        )
        response = lease_renewal_create_api(request, self.lease.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Only active or expired leases can be renewed")
