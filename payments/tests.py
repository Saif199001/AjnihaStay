from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Invoice, Payment
from .services import calculate_final_settlement, create_payment


class PaymentIntegrityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Owner Workspace", slug="owner-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Test Property", property_type="pg",
            address="Test Address", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="101", rent=Decimal("10000.00"))
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Test Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )
        self.occupancy = occupancy
        self.invoice = Invoice.objects.create(
            occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1),
        )
        self.client = APIClient()

    def payment_data(self, amount):
        return {
            "invoice": self.invoice.id, "amount": Decimal(amount), "payment_method": "upi",
            "payment_date": date(2026, 9, 3),
        }

    def test_invoice_rejects_negative_amounts(self):
        with self.assertRaises(ValidationError):
            Invoice.objects.create(
                occupancy=self.occupancy,
                billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1),
                rent_amount=Decimal("-1.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1),
            )

    def test_payment_rejects_non_positive_amount(self):
        with self.assertRaises(ValidationError):
            create_payment(self.owner, self.workspace, self.payment_data("0.00"))

    def test_payment_cannot_overpay_invoice(self):
        create_payment(self.owner, self.workspace, self.payment_data("7000.00"))
        with self.assertRaises(ValidationError):
            create_payment(self.owner, self.workspace, self.payment_data("4000.00"))

    def test_payment_is_workspace_scoped(self):
        with self.assertRaises(ValidationError):
            create_payment(self.other_owner, self.other_workspace, self.payment_data("1000.00"))

    def test_payment_updates_invoice_balance(self):
        create_payment(self.owner, self.workspace, self.payment_data("4000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")
        self.assertEqual(self.invoice.due_amount, Decimal("6000.00"))

    def test_full_payment_marks_invoice_paid(self):
        create_payment(self.owner, self.workspace, self.payment_data("10000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.due_amount, Decimal("0.00"))

    def test_invoice_save_reconciles_paid_amount_and_status_from_payments(self):
        create_payment(self.owner, self.workspace, self.payment_data("4000.00"))
        self.invoice.refresh_from_db()
        self.invoice.paid_amount = Decimal("9999.00")
        self.invoice.status = "paid"
        self.invoice.save()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")

    def test_invoice_cannot_reduce_total_below_actual_payments(self):
        create_payment(self.owner, self.workspace, self.payment_data("4000.00"))
        self.invoice.refresh_from_db()
        self.invoice.rent_amount = Decimal("3000.00")
        with self.assertRaises(ValidationError):
            self.invoice.save()

    def test_settlement_uses_actual_payment_rows(self):
        create_payment(self.owner, self.workspace, self.payment_data("4000.00"))
        self.invoice.paid_amount = Decimal("9999.00")
        self.invoice.status = "partial"
        self.invoice.save(update_fields=["paid_amount", "status"])

        settlement = calculate_final_settlement(self.occupancy.id, self.workspace)
        self.assertEqual(settlement["total_paid"], Decimal("4000.00"))
        self.assertEqual(settlement["total_due"], Decimal("6000.00"))

    def test_settlement_does_not_report_negative_due(self):
        create_payment(self.owner, self.workspace, self.payment_data("10000.00"))
        settlement = calculate_final_settlement(self.occupancy.id, self.workspace)
        self.assertEqual(settlement["total_due"], Decimal("0.00"))

    def test_database_constraint_blocks_invalid_payment_row(self):
        with self.assertRaises(IntegrityError):
            Payment.objects.bulk_create([
                Payment(
                    invoice=self.invoice,
                    amount=Decimal("0.00"),
                    payment_method="upi",
                    payment_date=date(2026, 9, 3),
                )
            ])


class PaymentWorkspaceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"
        self.owner = User.objects.create_user("api-owner@example.com", self.password)
        self.other = User.objects.create_user("api-other@example.com", self.password)
        self.manager = User.objects.create_user("api-manager@example.com", self.password)
        self.staff = User.objects.create_user("api-staff@example.com", self.password)

        self.workspace = Workspace.objects.create(name="API Workspace", slug="api-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other API Workspace", slug="other-api-workspace", owner=self.other)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="API Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(property=property_obj, unit_type="room", unit_number="201", rent=Decimal("12000.00"))
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="API Tenant",
            phone="8888888888", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("12000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1),
            rent_amount=Decimal("12000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1),
        )

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_WORKSPACE_ID": str((workspace or self.workspace).id)}

    def test_invoice_detail_rejects_cross_workspace_access(self):
        headers = self.authenticate(self.other, self.other_workspace)
        response = self.client.get(f"/api/invoices/{self.invoice.id}/", **headers)
        self.assertEqual(response.status_code, 404)

    def test_payment_create_requires_manager_role(self):
        headers = self.authenticate(self.staff)
        response = self.client.post("/api/payments/create/", {
            "invoice": self.invoice.id,
            "amount": "1000.00",
            "payment_method": "upi",
            "payment_date": "2026-09-03",
        }, format="json", **headers)
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_payment_in_workspace(self):
        headers = self.authenticate(self.manager)
        response = self.client.post("/api/payments/create/", {
            "invoice": self.invoice.id,
            "amount": "1000.00",
            "payment_method": "upi",
            "payment_date": "2026-09-03",
        }, format="json", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["invoice"], self.invoice.id)

    def test_cross_workspace_payment_create_is_blocked(self):
        headers = self.authenticate(self.other, self.other_workspace)
        response = self.client.post("/api/payments/create/", {
            "invoice": self.invoice.id,
            "amount": "1000.00",
            "payment_method": "upi",
            "payment_date": "2026-09-03",
        }, format="json", **headers)
        self.assertEqual(response.status_code, 400)

    def test_cross_workspace_payment_list_is_empty(self):
        create_payment(self.owner, self.workspace, {
            "invoice": self.invoice.id,
            "amount": Decimal("1000.00"),
            "payment_method": "upi",
            "payment_date": date(2026, 9, 3),
        })
        headers = self.authenticate(self.other, self.other_workspace)
        response = self.client.get(f"/api/payments/?invoice={self.invoice.id}", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_malformed_payment_list_invoice_id_returns_400(self):
        headers = self.authenticate(self.staff)
        response = self.client.get("/api/payments/?invoice=not-a-number", **headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid invoice ID")

    def test_zero_payment_list_invoice_id_returns_400(self):
        headers = self.authenticate(self.staff)
        response = self.client.get("/api/payments/?invoice=0", **headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid invoice ID")

    def test_cross_workspace_final_settlement_is_blocked(self):
        headers = self.authenticate(self.other, self.other_workspace)
        response = self.client.get(f"/api/final-settlement/{self.occupancy.id}/", **headers)
        self.assertEqual(response.status_code, 404)
