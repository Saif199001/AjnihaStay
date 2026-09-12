from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from leasing.api import lease_create_api, lease_detail_api, lease_list_api, lease_transition_api, lease_update_api
from leasing.models import Lease
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(email="p14-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="p14-manager@example.com", password="pass")
        self.member = User.objects.create_user(email="p14-member@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="P14 Workspace", slug="p14-workspace", owner=self.owner)
        for user, role in ((self.owner, "owner"), (self.manager, "manager"), (self.member, "staff")):
            Membership.objects.create(workspace=self.workspace, user=user, role=role, is_active=True)
        prop = Property.objects.create(owner=self.owner, workspace=self.workspace, name="P14 Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=prop, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="P14 Tenant", phone="9999999999", email="p14-tenant@example.com", permanent_address="Lucknow")
        self.occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026,1,1), check_out_date=date(2026,12,31), next_due_date=date(2026,1,1), is_active=True)

    def auth(self, request, user, workspace=None):
        force_authenticate(request, user=user)
        request.workspace = workspace or self.workspace
        return request

    def unauth(self, request, workspace=None):
        request.workspace = workspace or self.workspace
        return request

    def payload(self):
        return {"occupancy": self.occupancy.id, "start_date": "2026-01-01", "end_date": "2026-12-31", "rent_amount": "12000.00", "security_deposit": "24000.00"}

    def create_lease(self):
        response = lease_create_api(self.auth(self.factory.post("/api/leases/create/", self.payload(), format="json"), self.manager))
        self.assertEqual(response.status_code, 201)
        return response.data["data"]["id"]

    def test_create_endpoint_returns_201(self):
        self.assertEqual(self.create_lease() is not None, True)

    def test_list_and_detail_are_workspace_scoped(self):
        lease_id = self.create_lease()
        response = lease_list_api(self.auth(self.factory.get("/api/leases/"), self.member))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        detail = lease_detail_api(self.auth(self.factory.get(f"/api/leases/{lease_id}/"), self.member), lease_id)
        self.assertEqual(detail.status_code, 200)

        other_owner = User.objects.create_user(email="p14-other-list@example.com", password="pass")
        other = Workspace.objects.create(name="Other P14 List", slug="other-p14-list", owner=other_owner)
        Membership.objects.create(workspace=other, user=other_owner, role="owner", is_active=True)
        other_list = lease_list_api(self.auth(self.factory.get("/api/leases/"), other_owner, other))
        self.assertEqual(other_list.status_code, 200)
        self.assertEqual(other_list.data["data"], [])

    def test_write_endpoints_require_manager_permission(self):
        create_request = self.auth(self.factory.post("/api/leases/create/", self.payload(), format="json"), self.member)
        self.assertEqual(lease_create_api(create_request).status_code, 403)

        lease_id = self.create_lease()
        update_request = self.auth(self.factory.post(f"/api/leases/{lease_id}/update/", {"agreement_number": "P14-001"}, format="json"), self.member)
        self.assertEqual(lease_update_api(update_request, lease_id).status_code, 403)

        transition_request = self.auth(self.factory.post(f"/api/leases/{lease_id}/transition/", {"status": Lease.STATUS_PENDING_SIGNATURE}, format="json"), self.member)
        self.assertEqual(lease_transition_api(transition_request, lease_id).status_code, 403)

    def test_unauthenticated_requests_are_rejected(self):
        for view, request, args in (
            (lease_list_api, self.factory.get("/api/leases/"), ()),
            (lease_detail_api, self.factory.get("/api/leases/1/"), (1,)),
            (lease_create_api, self.factory.post("/api/leases/create/", self.payload(), format="json"), ()),
            (lease_update_api, self.factory.post("/api/leases/1/update/", {}, format="json"), (1,)),
            (lease_transition_api, self.factory.post("/api/leases/1/transition/", {"status": Lease.STATUS_PENDING_SIGNATURE}, format="json"), (1,)),
        ):
            self.assertEqual(view(self.unauth(request), *args).status_code, 403)

    def test_detail_returns_404_for_wrong_workspace(self):
        lease_id = self.create_lease()
        other_owner = User.objects.create_user(email="p14-other@example.com", password="pass")
        other = Workspace.objects.create(name="Other P14", slug="other-p14", owner=other_owner)
        Membership.objects.create(workspace=other, user=other_owner, role="owner", is_active=True)
        detail = lease_detail_api(self.auth(self.factory.get(f"/api/leases/{lease_id}/"), other_owner, other), lease_id)
        self.assertEqual(detail.status_code, 404)

    def test_transition_validation_is_exposed_as_400(self):
        lease_id = self.create_lease()
        transition = lease_transition_api(self.auth(self.factory.post(f"/api/leases/{lease_id}/transition/", {"status": Lease.STATUS_ACTIVE}, format="json"), self.manager), lease_id)
        self.assertEqual(transition.status_code, 400)

    def test_serializer_rejects_invalid_date_and_negative_money(self):
        bad = self.payload()
        bad["end_date"] = "2025-12-31"
        response = lease_create_api(self.auth(self.factory.post("/api/leases/create/", bad, format="json"), self.manager))
        self.assertEqual(response.status_code, 400)

        bad = self.payload()
        bad["rent_amount"] = "-1.00"
        response = lease_create_api(self.auth(self.factory.post("/api/leases/create/", bad, format="json"), self.manager))
        self.assertEqual(response.status_code, 400)

    def test_transition_endpoint_requires_valid_target_status(self):
        lease_id = self.create_lease()
        response = lease_transition_api(self.auth(self.factory.post(f"/api/leases/{lease_id}/transition/", {"status": "not-a-status"}, format="json"), self.manager), lease_id)
        self.assertEqual(response.status_code, 400)
