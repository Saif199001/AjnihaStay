from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .billing_models import BillingSchedule


class BillingScheduleAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("schedule-owner@example.com", password)
        self.manager = User.objects.create_user("schedule-manager@example.com", password)
        self.staff = User.objects.create_user("schedule-staff@example.com", password)
        self.other = User.objects.create_user("schedule-other@example.com", password)

        self.workspace = Workspace.objects.create(
            name="Schedule Workspace", slug="schedule-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Schedule Workspace", slug="other-schedule-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Schedule Property",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="501", rent=Decimal("10000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Schedule Tenant",
            phone="7777777777", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )

    def headers(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_WORKSPACE_ID": str((workspace or self.workspace).id)}

    def payload(self, **overrides):
        data = {
            "occupancy": self.occupancy.id,
            "frequency": "monthly",
            "amount": "10000.00",
            "next_run_date": "2026-10-01",
            "active": True,
        }
        data.update(overrides)
        return data

    def test_manager_can_create_schedule_without_financial_side_effects(self):
        response = self.client.post(
            "/api/billing-schedules/create/",
            self.payload(),
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["frequency"], "monthly")
        self.assertTrue(BillingSchedule.objects.filter(occupancy=self.occupancy).exists())
        self.assertEqual(self.occupancy.invoices.count(), 0)
        self.assertEqual(self.occupancy.charges.count(), 0)

    def test_staff_cannot_create_schedule(self):
        response = self.client.post(
            "/api/billing-schedules/create/",
            self.payload(),
            format="json",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_list_schedule(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy, frequency="monthly", amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        response = self.client.get(
            "/api/billing-schedules/",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["id"], schedule.id)

    def test_cross_workspace_create_is_rejected(self):
        response = self.client.post(
            "/api/billing-schedules/create/",
            self.payload(occupancy=999999),
            format="json",
            **self.headers(self.owner, self.other_workspace),
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_update_schedule(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy, frequency="monthly", amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        response = self.client.patch(
            f"/api/billing-schedules/{schedule.id}/update/",
            {"amount": "11000.00", "active": False},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 200)
        schedule.refresh_from_db()
        self.assertEqual(schedule.amount, Decimal("11000.00"))
        self.assertFalse(schedule.active)

    def test_staff_cannot_update_schedule(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy, frequency="monthly", amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        response = self.client.patch(
            f"/api/billing-schedules/{schedule.id}/update/",
            {"amount": "11000.00"},
            format="json",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 403)
        schedule.refresh_from_db()
        self.assertEqual(schedule.amount, Decimal("10000.00"))

    def test_cross_workspace_schedule_is_hidden(self):
        schedule = BillingSchedule.objects.create(
            occupancy=self.occupancy, frequency="monthly", amount=Decimal("10000.00"),
            next_run_date=date(2026, 10, 1),
        )
        response = self.client.get(
            f"/api/billing-schedules/{schedule.id}/",
            **self.headers(self.other, self.other_workspace),
        )
        self.assertEqual(response.status_code, 404)
