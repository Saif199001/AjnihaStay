from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from payments.services import create_payment
from properties.models import Property
from tenant.models import Tenant
from tenant.services import create_occupancy
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace

from .services import get_dashboard_data


class DashboardReadModelTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = User.objects.create_user("dashboard-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("dashboard-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Dashboard Workspace", slug="dashboard-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Dashboard Other Workspace", slug="dashboard-other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        self.property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Dashboard Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000.00"), capacity=2)
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Dashboard Tenant", phone="9999999998", permanent_address="Delhi")

    def test_dashboard_reports_capacity_aware_availability_and_upcoming_vacancy(self):
        occupancy = create_occupancy(self.owner, self.workspace, {"tenant": self.tenant, "unit": self.unit, "rent": Decimal("10000.00"), "billing_type": "advance", "billing_cycle": "monthly", "check_in_date": self.today - timedelta(days=10), "check_out_date": self.today + timedelta(days=5), "next_due_date": self.today + timedelta(days=10), "security_deposit": Decimal("2000.00"), "deposit_paid": True})
        data = get_dashboard_data(self.workspace)
        self.assertEqual(data["summary"]["total_properties"], 1)
        self.assertEqual(data["summary"]["total_units"], 1)
        self.assertEqual(data["summary"]["total_unit_capacity"], 2)
        self.assertEqual(data["summary"]["occupied_unit_slots"], 1)
        self.assertEqual(data["summary"]["available_unit_slots"], 1)
        self.assertEqual(data["summary"]["active_tenants"], 1)
        self.assertEqual(len(data["availability"]), 1)
        self.assertEqual(data["availability"][0]["unit_id"], self.unit.id)
        self.assertEqual(data["availability"][0]["available_capacity"], 1)
        self.assertEqual(data["availability"][0]["type"], "unit")
        self.assertEqual(len(data["upcoming_vacancies"]), 1)
        self.assertEqual(data["upcoming_vacancies"][0]["occupancy_id"], occupancy.id)
        self.assertEqual(data["upcoming_vacancies"][0]["vacancy_date"], self.today + timedelta(days=5))

    def test_dashboard_lists_vacant_subunits_without_consuming_unit_capacity(self):
        subunit_a = SubUnit.objects.create(unit=self.unit, subunit_number="A", rent=Decimal("6000.00"))
        subunit_b = SubUnit.objects.create(unit=self.unit, subunit_number="B", rent=Decimal("6000.00"))
        subtenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Subunit Tenant", phone="9999999997", permanent_address="Delhi")
        create_occupancy(self.owner, self.workspace, {"tenant": subtenant, "unit": self.unit, "subunit": subunit_a, "rent": Decimal("6000.00"), "billing_type": "advance", "billing_cycle": "monthly", "check_in_date": self.today - timedelta(days=3), "next_due_date": self.today + timedelta(days=27), "security_deposit": Decimal("1000.00"), "deposit_paid": True})
        data = get_dashboard_data(self.workspace)
        self.assertEqual(data["summary"]["total_subunits"], 2)
        self.assertEqual(data["summary"]["occupied_subunits"], 1)
        self.assertEqual(data["summary"]["available_subunits"], 1)
        self.assertEqual(data["summary"]["available_unit_slots"], 2)
        subunit_spaces = [item for item in data["availability"] if item["type"] == "subunit"]
        self.assertEqual(len(subunit_spaces), 1)
        self.assertEqual(subunit_spaces[0]["subunit_id"], subunit_b.id)

    def test_dashboard_financials_are_workspace_isolated(self):
        occupancy = create_occupancy(self.owner, self.workspace, {"tenant": self.tenant, "unit": self.unit, "rent": Decimal("10000.00"), "billing_type": "advance", "billing_cycle": "monthly", "check_in_date": self.today - timedelta(days=2), "next_due_date": self.today + timedelta(days=28), "security_deposit": Decimal("2000.00"), "deposit_paid": True})
        invoice = occupancy.invoices.get()
        create_payment(self.owner, self.workspace, {"invoice": invoice.id, "amount": Decimal("4000.00"), "payment_method": "upi", "payment_date": self.today})
        other_property = Property.objects.create(owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110002")
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="201", rent=Decimal("8000.00"))
        other_tenant = Tenant.objects.create(owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant", phone="9999999996", permanent_address="Delhi")
        other_occupancy = create_occupancy(self.other_owner, self.other_workspace, {"tenant": other_tenant, "unit": other_unit, "rent": Decimal("8000.00"), "billing_type": "advance", "billing_cycle": "monthly", "check_in_date": self.today - timedelta(days=1), "next_due_date": self.today + timedelta(days=29), "security_deposit": Decimal("1000.00"), "deposit_paid": True})
        other_invoice = other_occupancy.invoices.get()
        create_payment(self.other_owner, self.other_workspace, {"invoice": other_invoice.id, "amount": Decimal("8000.00"), "payment_method": "cash", "payment_date": self.today})
        data = get_dashboard_data(self.workspace)
        self.assertEqual(data["financial"]["period_collected"], Decimal("4000.00"))
        self.assertEqual(data["financial"]["outstanding"], Decimal("6000.00"))
        self.assertEqual(data["summary"]["total_properties"], 1)
        self.assertEqual(data["summary"]["total_units"], 1)
        self.assertNotEqual(data["financial"]["period_collected"], Decimal("12000.00"))


class DashboardEmptyWorkspaceTests(TestCase):
    def test_empty_workspace_returns_zero_metrics_and_empty_lists(self):
        owner = User.objects.create_user("dashboard-empty@example.com", "StrongPass123!")
        workspace = Workspace.objects.create(name="Empty Dashboard Workspace", slug="empty-dashboard-workspace", owner=owner)
        Membership.objects.create(workspace=workspace, user=owner, role="owner")
        data = get_dashboard_data(workspace)
        self.assertEqual(data["summary"]["total_properties"], 0)
        self.assertEqual(data["summary"]["total_units"], 0)
        self.assertEqual(data["summary"]["available_unit_slots"], 0)
        self.assertEqual(data["summary"]["occupancy_rate"], 0)
        self.assertEqual(data["financial"]["period_collected"], Decimal("0"))
        self.assertEqual(data["availability"], [])
        self.assertEqual(data["upcoming_vacancies"], [])

    @patch("dashboard.services.timezone.localdate")
    def test_dashboard_uses_django_localdate_for_as_of_and_current_occupancy(self, localdate):
        localdate.return_value = date(2026, 9, 5)
        data = get_dashboard_data(self.workspace)
        self.assertEqual(data["as_of"], date(2026, 9, 5))
        self.assertEqual(data["period"], {"start": date(2026, 9, 1), "end": date(2026, 9, 5)})


class DashboardAPIContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user("dashboard-api@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Dashboard API Workspace", slug="dashboard-api-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.client.force_authenticate(self.owner)

    def test_dashboard_api_returns_contract_and_accepts_period_parameters(self):
        start = date(2026, 8, 1)
        end = date(2026, 8, 31)
        response = self.client.get("/api/dashboard/", {"period_start": start.isoformat(), "period_end": end.isoformat(), "upcoming_days": 14}, HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["start"], start)
        self.assertEqual(response.data["period"]["end"], end)
        self.assertEqual(response.data["availability"], [])
        self.assertEqual(response.data["upcoming_vacancies"], [])
        self.assertIn("summary", response.data)
        self.assertIn("financial", response.data)

    def test_dashboard_api_rejects_invalid_period_and_upcoming_days(self):
        response = self.client.get("/api/dashboard/", {"period_start": "2026-09-10", "period_end": "2026-09-01"}, HTTP_X_WORKSPACE_ID=str(self.workspace.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("period_end", response.data)
        for value in ("0", "91"):
            response = self.client.get("/api/dashboard/", {"upcoming_days": value}, HTTP_X_WORKSPACE_ID=str(self.workspace.id))
            self.assertEqual(response.status_code, 400)

    def test_dashboard_api_requires_workspace_membership(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 401)
