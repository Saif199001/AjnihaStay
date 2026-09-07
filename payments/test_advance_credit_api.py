from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from payments.models import AdvanceCredit, Invoice, Payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class AdvanceCreditAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("advance-api-owner@example.com", password)
        self.manager = User.objects.create_user("advance-api-manager@example.com", password)
        self.staff = User.objects.create_user("advance-api-staff@example.com", password)
        self.other_owner = User.objects.create_user("advance-api-other@example.com", password)

        self.workspace = Workspace.objects.create(
            name="Advance API Workspace",
            slug="advance-api-workspace",
            owner=self.owner,
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Advance API Workspace",
            slug="other-advance-api-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Advance API Tenant",
            phone="8888888888",
            permanent_address="Delhi",
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Advance API Property",
            property_type="pg",
            address="API Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="API-1",
            rent=Decimal("10000.00"),
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 7),
        )

    def headers(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_WORKSPACE_ID": str((workspace or self.workspace).id)}

    def create_credit(self, amount="6000.00"):
        response = self.client.post(
            "/api/advance-credits/",
            {
                "payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": amount,
            },
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 201)
        return AdvanceCredit.objects.get(id=response.data["data"]["id"])

    def test_manager_can_create_advance_credit(self):
        response = self.client.post(
            "/api/advance-credits/",
            {
                "payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": "6000.00",
            },
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["original_amount"], "6000.00")
        self.assertEqual(response.data["data"]["available_amount"], "6000.00")
        self.assertEqual(response.data["data"]["applications"], [])

    def test_staff_cannot_create_advance_credit(self):
        response = self.client.post(
            "/api/advance-credits/",
            {
                "payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": "6000.00",
            },
            format="json",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AdvanceCredit.objects.exists())

    def test_staff_can_list_and_detail_advance_credit(self):
        credit = self.create_credit()

        list_response = self.client.get(
            "/api/advance-credits/",
            **self.headers(self.staff),
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["data"][0]["id"], credit.id)

        detail_response = self.client.get(
            f"/api/advance-credits/{credit.id}/",
            **self.headers(self.staff),
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["data"]["available_amount"], "6000.00")

    def test_cross_workspace_credit_is_hidden(self):
        credit = self.create_credit()
        response = self.client.get(
            f"/api/advance-credits/{credit.id}/",
            **self.headers(self.other_owner, self.other_workspace),
        )
        self.assertEqual(response.status_code, 404)

    def test_manager_can_apply_credit_and_invoice_state_updates(self):
        credit = self.create_credit()
        response = self.client.post(
            f"/api/advance-credits/{credit.id}/apply/",
            {"invoice": self.invoice.id, "amount": "4000.00"},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["application"]["amount"], "4000.00")
        self.assertEqual(response.data["data"]["remaining_credit"], Decimal("2000.00"))
        self.assertEqual(response.data["data"]["invoice"]["paid_amount"], "4000.00")
        self.assertEqual(response.data["data"]["invoice"]["status"], "partial")
        self.assertEqual(response.data["data"]["invoice"]["due_amount"], "6000.00")
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 0)

    def test_staff_cannot_apply_credit(self):
        credit = self.create_credit()
        response = self.client.post(
            f"/api/advance-credits/{credit.id}/apply/",
            {"invoice": self.invoice.id, "amount": "1000.00"},
            format="json",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_workspace_apply_is_rejected(self):
        credit = self.create_credit()
        response = self.client.post(
            f"/api/advance-credits/{credit.id}/apply/",
            {"invoice": self.invoice.id, "amount": "1000.00"},
            format="json",
            **self.headers(self.other_owner, self.other_workspace),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have permission to perform this action.")

    def test_invalid_amount_is_rejected_by_serializer(self):
        response = self.client.post(
            "/api/advance-credits/",
            {
                "payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": "0.00",
            },
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data)
