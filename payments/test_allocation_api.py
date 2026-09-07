from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Invoice, Payment, PaymentAllocation
from .services import record_payment


class PaymentAllocationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("allocation-owner@example.com", password)
        self.manager = User.objects.create_user("allocation-manager@example.com", password)
        self.staff = User.objects.create_user("allocation-staff@example.com", password)
        self.other = User.objects.create_user("allocation-other@example.com", password)

        self.workspace = Workspace.objects.create(
            name="Allocation Workspace", slug="allocation-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Allocation Workspace", slug="other-allocation-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Allocation Property",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="301", rent=Decimal("10000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Allocation Tenant",
            phone="7777777777", permanent_address="Delhi",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1),
        )

    def headers(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_WORKSPACE_ID": str((workspace or self.workspace).id)}

    def make_unallocated_payment(self, amount="6000.00"):
        return Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal(amount),
            payment_method="upi",
            payment_date=date(2026, 9, 3),
        )

    def test_manager_can_allocate_payment(self):
        payment = self.make_unallocated_payment()
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "4000.00"}]},
            format="json",
            **self.headers(self.manager),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message"], "Payment allocated")
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["invoice"], self.invoice.id)
        self.assertEqual(Decimal(response.data["data"][0]["amount"]), Decimal("4000.00"))
        self.assertTrue(PaymentAllocation.objects.filter(payment=payment, invoice=self.invoice).exists())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")

    def test_staff_cannot_allocate_payment(self):
        payment = self.make_unallocated_payment()
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "1000.00"}]},
            format="json",
            **self.headers(self.staff),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())

    def test_cross_workspace_payment_is_rejected(self):
        payment = self.make_unallocated_payment()
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "1000.00"}]},
            format="json",
            **self.headers(self.other, self.other_workspace),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Payment not found")

    def test_invalid_allocation_shape_is_rejected_by_serializer(self):
        payment = self.make_unallocated_payment()
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "0.00"}]},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("allocations", response.data)
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())

    def test_over_allocation_is_rejected_by_canonical_service(self):
        payment = self.make_unallocated_payment("5000.00")
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "6000.00"}]},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Allocation exceeds payment amount")
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())

    def test_invoice_over_allocation_is_rejected_by_canonical_service(self):
        payment = self.make_unallocated_payment("20000.00")
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "10001.00"}]},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Allocation exceeds invoice remaining amount")
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())

    def test_multi_invoice_allocation_is_atomic(self):
        second_invoice = Invoice.objects.create(
            occupancy=self.invoice.occupancy,
            billing_start=date(2026, 10, 1), billing_end=date(2026, 11, 1),
            rent_amount=Decimal("5000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 11, 1),
        )
        payment = self.make_unallocated_payment("10000.00")
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [
                {"invoice": self.invoice.id, "amount": "4000.00"},
                {"invoice": second_invoice.id, "amount": "6000.00"},
            ]},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Allocation exceeds invoice remaining amount")
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())

    @patch("payments.api.allocate_payment")
    def test_allocation_api_delegates_to_canonical_service(self, allocate_payment_mock):
        payment = self.make_unallocated_payment("2000.00")
        allocation = PaymentAllocation(
            payment=payment, invoice=self.invoice, amount=Decimal("1000.00")
        )
        allocate_payment_mock.return_value = [allocation]

        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "1000.00"}]},
            format="json",
            **self.headers(self.manager),
        )

        self.assertEqual(response.status_code, 201)
        allocate_payment_mock.assert_called_once_with(
            self.manager,
            self.workspace,
            payment.id,
            [{"invoice": self.invoice.id, "amount": Decimal("1000.00")}],
        )

    def test_existing_legacy_payment_can_remain_unmodified(self):
        payment = record_payment(self.owner, self.workspace, {
            "invoice": self.invoice.id,
            "amount": Decimal("1000.00"),
            "payment_method": "upi",
            "payment_date": date(2026, 9, 3),
        })
        response = self.client.post(
            f"/api/payments/{payment.id}/allocations/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "1000.00"}]},
            format="json",
            **self.headers(self.manager),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "Allocation exceeds payment amount",
        )
