from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .models import Invoice


class FinancialReportingAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("reporting-api-owner@example.com", "password")
        self.other_owner = User.objects.create_user("reporting-api-other@example.com", "password")
        self.workspace = Workspace.objects.create(name="API Workspace", slug="api-reporting", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other API Workspace", slug="other-api-reporting", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        property_obj = Property.objects.create(owner=self.owner, workspace=self.workspace, name="API Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="701", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="API Tenant", phone="9999999998", permanent_address="Delhi")
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("12000.00"), check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30), next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False)
        self.invoice = Invoice.objects.create(occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30), rent_amount=Decimal("12000.00"), charges_amount=Decimal("500.00"), due_date=date(2026, 9, 30))
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def _get(self, path, **params):
        return self.client.get(path, params, HTTP_X_WORKSPACE_ID=str(self.workspace.pk))

    def test_receivables_endpoint_is_read_only_and_decimal_safe(self):
        before = Invoice.objects.get(pk=self.invoice.pk)
        response = self._get("/api/reports/receivables/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["outstanding"], "12500.00")
        self.assertEqual(response.data["data"]["invoices"][0]["gross_receivable"], "12500.00")
        after = Invoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((before.total_amount, before.paid_amount, before.status), (after.total_amount, after.paid_amount, after.status))

    def test_collection_period_requires_valid_dates(self):
        response = self._get("/api/reports/collections/period/", start="bad", end="2026-09-30")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid start date")

    def test_aging_endpoint_requires_as_of(self):
        response = self._get("/api/reports/aging/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "as_of is required")

    def test_invoice_endpoint_is_workspace_scoped(self):
        response = self.client.get("/api/reports/invoice/", {"invoice_id": self.invoice.pk}, HTTP_X_WORKSPACE_ID=str(self.other_workspace.pk))
        self.assertEqual(response.status_code, 403)

    def test_reporting_endpoints_require_workspace_membership(self):
        outsider = User.objects.create_user("reporting-api-outsider@example.com", "password")
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.get("/api/reports/receivables/", HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
        self.assertEqual(response.status_code, 403)

    def test_reporting_endpoints_are_get_only(self):
        response = self.client.post("/api/reports/receivables/", {}, HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
        self.assertEqual(response.status_code, 405)

    def test_all_core_report_routes_are_reachable(self):
        paths = [
            ("/api/reports/receivables/", {}),
            ("/api/reports/invoice-status/", {}),
            ("/api/reports/collections/period/", {"start": "2026-09-01", "end": "2026-09-30"}),
            ("/api/reports/aging/", {"as_of": "2026-09-30"}),
            ("/api/reports/advance-credits/", {}),
            ("/api/reports/adjustments/", {}),
            ("/api/reports/late-fees/", {}),
            ("/api/reports/ledger/", {}),
            ("/api/reports/reconciliation/", {}),
        ]
        for path, params in paths:
            with self.subTest(path=path):
                response = self._get(path, **params)
                self.assertEqual(response.status_code, 200)
                self.assertIn("data", response.data)
