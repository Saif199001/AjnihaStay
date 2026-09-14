from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from leasing.api import lease_renewal_cancel_api, lease_renewal_confirm_api, lease_renewal_create_api
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
        self.workspace = Workspace.objects.create(name="P15 API Workspace", slug="p15-api-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)

    def test_terminal_source_lease_cannot_be_renewed(self):
        from leasing.termination_service import terminate_lease
        terminate_lease(
            self.manager,
            self.workspace,
            self.lease.id,
            reason="P15 API terminal source test",
            effective_date=timezone.localdate(),
        )
        response = lease_renewal_create_api(
            self.auth(self.factory.post(f"/api/leases/{self.lease.id}/renewals/create/", self.payload(), format="json")),
            self.lease.id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Only active or expired leases can be renewed")
