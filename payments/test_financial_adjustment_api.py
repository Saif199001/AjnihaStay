from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from payments.models import FinancialAdjustment, Invoice
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class FinancialAdjustmentAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("adjustment-api@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Adjustment API Workspace",
            slug="adjustment-api-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=Membership.ROLE_OWNER,
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Adjustment API Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Adjustment API Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="A-1",
            rent=Decimal("10000.00"),
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
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
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def post_adjustment(self, **overrides):
        data = {
            "invoice": self.invoice.id,
            "adjustment_type": "credit",
            "amount": "1000.00",
            "reason": "Approved API credit",
            "reference": "API-CASE-1",
            "idempotency_key": "API-ADJ-1",
        }
        data.update(overrides)
        return self.client.post(
            "/api/financial-adjustments/create/",
            data,
            format="json",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )

    def test_manager_can_create_adjustment_and_receive_financial_position(self):
        response = self.post_adjustment()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message"], "Financial adjustment created")
        self.assertTrue(response.data["data"]["created"])
        self.assertEqual(response.data["data"]["adjustment"]["invoice"], self.invoice.id)
        self.assertEqual(response.data["data"]["adjustment"]["amount"], "1000.00")
        self.assertEqual(
            response.data["data"]["financial_position"]["outstanding"],
            "9000.00",
        )
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_idempotent_retry_returns_existing_adjustment(self):
        first = self.post_adjustment()
        second = self.post_adjustment()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["message"], "Financial adjustment already exists")
        self.assertFalse(second.data["data"]["created"])
        self.assertEqual(
            first.data["data"]["adjustment"]["id"],
            second.data["data"]["adjustment"]["id"],
        )
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_staff_cannot_create_adjustment(self):
        staff = User.objects.create_user("adjustment-api-staff@example.com", "StrongPass123!")
        Membership.objects.create(
            workspace=self.workspace,
            user=staff,
            role=Membership.ROLE_STAFF,
        )
        self.client.force_authenticate(user=staff)

        response = self.post_adjustment()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(FinancialAdjustment.objects.count(), 0)

    def test_cross_workspace_invoice_is_hidden_from_api(self):
        other_owner = User.objects.create_user("adjustment-api-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Adjustment API Workspace",
            slug="other-adjustment-api-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role=Membership.ROLE_OWNER,
        )
        self.client.force_authenticate(user=other_owner)

        response = self.client.post(
            "/api/financial-adjustments/create/",
            {
                "invoice": self.invoice.id,
                "adjustment_type": "credit",
                "amount": "100.00",
                "reason": "Cross workspace API attempt",
            },
            format="json",
            HTTP_X_WORKSPACE_ID=str(other_workspace.id),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Invoice not found")
        self.assertEqual(FinancialAdjustment.objects.count(), 0)

    def test_invalid_adjustment_payload_is_rejected_before_mutation(self):
        response = self.post_adjustment(amount="0.00")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FinancialAdjustment.objects.count(), 0)
