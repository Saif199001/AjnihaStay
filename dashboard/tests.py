from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.services import get_dashboard_data
from payments.models import Invoice, Payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace


User = get_user_model()


class DashboardReadModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dashboard-owner", email="dashboard@example.com", password="testpass123")
        self.workspace = Workspace.objects.create(name="Dashboard Workspace", slug="dashboard-workspace", owner=self.user)
        Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")
        self.property = Property.objects.create(name="Main Property", owner=self.user, workspace=self.workspace)
        self.today = timezone.localdate()

    def test_dashboard_reports_capacity_aware_availability_and_upcoming_vacancy(self):
        unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000"), capacity=2)
        tenant = Tenant.objects.create(name="Current Tenant", email="current@example.com", phone="123", workspace=self.workspace, owner=self.user)
        Occupancy.objects.create(tenant=tenant, unit=unit, check_in=self.today - timedelta(days=5), check_out=self.today + timedelta(days=10), rent=Decimal("10000"), security_deposit=Decimal("0"), workspace=self.workspace)

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["summary"]["total_unit_capacity"], 2)
        self.assertEqual(data["summary"]["occupied_unit_slots"], 1)
        self.assertEqual(data["summary"]["available_unit_slots"], 1)
        self.assertEqual(data["availability"][0]["unit_id"], unit.id)
        self.assertEqual(data["upcoming_vacancies"][0]["vacancy_date"], self.today + timedelta(days=10))

    def test_dashboard_lists_vacant_subunits_without_consuming_unit_capacity(self):
        unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="102", rent=Decimal("12000"), capacity=3)
        occupied_subunit = SubUnit.objects.create(unit=unit, name="A")
        vacant_subunit = SubUnit.objects.create(unit=unit, name="B")
        tenant = Tenant.objects.create(name="Sub Tenant", email="sub@example.com", phone="123", workspace=self.workspace, owner=self.user)
        Occupancy.objects.create(tenant=tenant, unit=unit, subunit=occupied_subunit, check_in=self.today - timedelta(days=2), rent=Decimal("12000"), security_deposit=Decimal("0"), workspace=self.workspace)

        data = get_dashboard_data(self.workspace)
        vacant = [item for item in data["availability"] if item["type"] == "subunit"]

        self.assertEqual(data["summary"]["occupied_unit_slots"], 0)
        self.assertEqual(data["summary"]["available_unit_slots"], 3)
        self.assertEqual(data["summary"]["occupied_subunits"], 1)
        self.assertEqual(data["summary"]["available_subunits"], 1)
        self.assertEqual(len(vacant), 1)
        self.assertEqual(vacant[0]["subunit_id"], vacant_subunit.id)

    def test_dashboard_financials_are_workspace_isolated(self):
        other_user = User.objects.create_user(username="other-owner", email="other@example.com", password="testpass123")
        other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=other_user)
        Membership.objects.create(workspace=other_workspace, user=other_user, role="owner")
        tenant = Tenant.objects.create(name="Financial Tenant", email="financial@example.com", phone="123", workspace=self.workspace, owner=self.user)
        unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="103", rent=Decimal("5000"), capacity=1)
        occupancy = Occupancy.objects.create(tenant=tenant, unit=unit, check_in=self.today - timedelta(days=2), rent=Decimal("5000"), security_deposit=Decimal("0"), workspace=self.workspace)
        invoice = Invoice.objects.create(occupancy=occupancy, billing_start=self.today.replace(day=1), billing_end=self.today, rent_amount=Decimal("5000"), charges_amount=Decimal("0"))
        Payment.objects.create(invoice=invoice, amount=Decimal("1000"), payment_date=self.today)

        other_property = Property.objects.create(name="Other Property", owner=other_user, workspace=other_workspace)
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="201", rent=Decimal("9000"), capacity=1)
        other_tenant = Tenant.objects.create(name="Other Tenant", email="other-fin@example.com", phone="123", workspace=other_workspace, owner=other_user)
        other_occupancy = Occupancy.objects.create(tenant=other_tenant, unit=other_unit, check_in=self.today - timedelta(days=2), rent=Decimal("9000"), security_deposit=Decimal("0"), workspace=other_workspace)
        other_invoice = Invoice.objects.create(occupancy=other_occupancy, billing_start=self.today.replace(day=1), billing_end=self.today, rent_amount=Decimal("9000"), charges_amount=Decimal("0"))
        Payment.objects.create(invoice=other_invoice, amount=Decimal("9000"), payment_date=self.today)

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["financial"]["period_invoiced"], Decimal("5000"))
        self.assertEqual(data["financial"]["period_collected"], Decimal("1000"))


class DashboardEmptyWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="empty-owner", email="empty@example.com", password="testpass123")
        self.workspace = Workspace.objects.create(name="Empty Workspace", slug="empty-workspace", owner=self.user)
        Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")
        self.today = timezone.localdate()

    @patch("dashboard.services.timezone.localdate")
    def test_dashboard_uses_django_localdate_for_as_of_and_current_occupancy(self, mocked_localdate):
        mocked_localdate.return_value = date(2026, 9, 5)

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["as_of"], date(2026, 9, 5))
        self.assertEqual(data["period"]["start"], date(2026, 9, 1))
        self.assertEqual(data["period"]["end"], date(2026, 9, 5))

    def test_empty_workspace_returns_zero_metrics_and_empty_lists(self):
        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["summary"]["total_properties"], 0)
        self.assertEqual(data["summary"]["total_units"], 0)
        self.assertEqual(data["summary"]["total_unit_capacity"], 0)
        self.assertEqual(data["summary"]["occupied_unit_slots"], 0)
        self.assertEqual(data["summary"]["available_unit_slots"], 0)
        self.assertEqual(data["summary"]["active_tenants"], 0)
        self.assertEqual(data["availability"], [])
        self.assertEqual(data["upcoming_vacancies"], [])


class DashboardAPIContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="api-owner", email="api@example.com", password="testpass123")
        self.workspace = Workspace.objects.create(name="API Workspace", slug="api-workspace", owner=self.user)
        Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")

    def test_dashboard_api_returns_contract_and_accepts_period_parameters(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/dashboard/", {"period_start": "2026-08-01", "period_end": "2026-08-31", "upcoming_days": 45})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["start"], date(2026, 8, 1))
        self.assertEqual(response.data["period"]["end"], date(2026, 8, 31))
        self.assertEqual(response.data["summary"]["total_units"], 0)
        self.assertIn("financial", response.data)
        self.assertIn("availability", response.data)
        self.assertIn("upcoming_vacancies", response.data)

    def test_dashboard_api_rejects_invalid_period_and_upcoming_days(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/dashboard/", {"period_start": "2026-09-10", "period_end": "2026-09-01"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/dashboard/", {"upcoming_days": 0})
        self.assertEqual(response.status_code, 400)

    def test_dashboard_api_requires_workspace_membership(self):
        outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="testpass123")
        self.client.force_authenticate(user=outsider)
        response = self.client.get("/api/dashboard/")
        self.assertIn(response.status_code, (403, 404))
