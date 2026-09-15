from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from leasing.api import lease_renewal_cancel_api, lease_renewal_confirm_api, lease_renewal_create_api
from leasing.lease_service import create_lease, transition_lease
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent, LeaseRenewal
from leasing.models import Lease
from leasing.renewal_service import confirm_renewal, create_renewal
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class LeaseP15HardeningTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(email="p15-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="p15-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="P15 Workspace", slug="p15-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        prop = Property.objects.create(owner=self.owner, workspace=self.workspace, name="P15 Property", property_type="flat", address="Address", city="Lucknow", state="UP", pincode="226001")
        unit = Unit.objects.create(property=prop, unit_type="flat", unit_number="101", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="P15 Tenant", phone="9999999999", email="p15-tenant@example.com", permanent_address="Lucknow")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, rent=Decimal("12000.00"), security_deposit=Decimal("24000.00"), check_in_date=date(2026, 1, 1), check_out_date=date(2026, 12, 31), next_due_date=date(2026, 1, 1), is_active=True)
        lease = create_lease(self.manager, self.workspace, {"occupancy": occupancy, "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "rent_amount": Decimal("12000.00"), "security_deposit": Decimal("24000.00")})
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.lease = transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def renewal_data(self, **overrides):
        data = {"start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31), "rent_amount": Decimal("13500.00"), "security_deposit": Decimal("27000.00"), "notice_period_days": 30, "terms": {"pets": False}, "agreement_reference": "REN-001"}
        data.update(overrides)
        return data

    def auth(self, request, user=None):
        force_authenticate(request, user=user or self.manager)
        request.workspace = self.workspace
        return request

    def test_direct_model_status_save_is_rejected(self):
        lease = Lease.objects.get(pk=self.lease.pk)
        lease.status = Lease.STATUS_TERMINATED
        with self.assertRaises(ValidationError):
            lease.save()
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)

    def test_bulk_status_update_is_rejected(self):
        with self.assertRaises(ValidationError):
            Lease.objects.filter(pk=self.lease.pk).update(status=Lease.STATUS_EXPIRED)
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.STATUS_ACTIVE)

    def test_confirmed_renewal_is_immutable(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())
        confirm_renewal(self.manager, self.workspace, renewal.id)
        renewal.refresh_from_db()
        renewal.rent_amount = Decimal("99999.00")
        with self.assertRaises(ValidationError):
            renewal.save()
        successor = LeaseContractVersion.objects.get(pk=renewal.successor_version_id)
        successor.rent_amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            successor.save()

    def test_confirmed_renewal_cannot_be_reconfirmed_into_new_version(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())
        first = confirm_renewal(self.manager, self.workspace, renewal.id)
        second = confirm_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(first.successor_version_id, second.successor_version_id)
        self.assertEqual(LeaseContractVersion.objects.filter(lease=self.lease).count(), 2)
        self.assertEqual(LeaseLifecycleEvent.objects.filter(lease=self.lease, event_type=LeaseLifecycleEvent.EVENT_RENEWED).count(), 1)

    def test_renewal_confirmation_records_single_successor_and_event(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())
        confirmed = confirm_renewal(self.manager, self.workspace, renewal.id)
        self.assertEqual(confirmed.status, LeaseRenewal.STATUS_CONFIRMED)
        self.assertEqual(LeaseContractVersion.objects.filter(lease=self.lease).count(), 2)
        self.assertEqual(LeaseLifecycleEvent.objects.filter(lease=self.lease, event_key=f"renewal:{renewal.id}").count(), 1)

    def test_renewal_api_create_confirm_cancel_contract(self):
        payload = {"start_date": "2027-01-01", "end_date": "2027-12-31", "rent_amount": "13500.00", "security_deposit": "27000.00"}
        response = lease_renewal_create_api(self.auth(self.factory.post(f"/api/leases/{self.lease.id}/renewals/create/", payload, format="json")), self.lease.id)
        self.assertEqual(response.status_code, 201)
        renewal_id = response.data["data"]["id"]
        response = lease_renewal_confirm_api(self.auth(self.factory.post(f"/api/leases/renewals/{renewal_id}/confirm/", {}, format="json")), renewal_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], LeaseRenewal.STATUS_CONFIRMED)

        second = create_renewal(self.manager, self.workspace, self.lease.id, {"start_date": date(2028, 1, 1), "end_date": date(2028, 12, 31)})
        response = lease_renewal_cancel_api(self.auth(self.factory.post(f"/api/leases/renewals/{second.id}/cancel/", {}, format="json")), second.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], LeaseRenewal.STATUS_CANCELLED)

    def test_renewal_api_requires_manager(self):
        member = User.objects.create_user(email="p15-member@example.com", password="pass")
        Membership.objects.create(workspace=self.workspace, user=member, role="member", is_active=True)
        payload = {"start_date": "2027-01-01", "end_date": "2027-12-31"}
        request = self.auth(self.factory.post(f"/api/leases/{self.lease.id}/renewals/create/", payload, format="json"), member)
        response = lease_renewal_create_api(request, self.lease.id)
        self.assertEqual(response.status_code, 403)
