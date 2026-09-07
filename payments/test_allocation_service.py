from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("allocation-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("allocation-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Allocation Workspace", slug="allocation-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Tenant One", phone="9999999999", permanent_address="Delhi")
        self.property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Property One", property_type="pg", address="Test Address", city="Delhi", state="Delhi", pincode="110001")
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="A-1", rent=Decimal("10000.00"))
        self.occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 1, 1), next_due_date=date(2026, 2, 1), billing_type="arrears", billing_cycle="monthly")
        self.invoice_a = Invoice.objects.create(occupancy=self.occupancy, billing_start=date(2026, 1, 1), billing_end=date(2026, 1, 31), rent_amount=Decimal("6000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 2, 5))
        self.invoice_b = Invoice.objects.create(occupancy=self.occupancy, billing_start=date(2026, 2, 1), billing_end=date(2026, 2, 28), rent_amount=Decimal("4000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 3, 5))
        self.payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000.00"), payment_method="bank", payment_date=date(2026, 9, 6))

    def test_allocates_one_payment_across_multiple_invoices(self):
        allocations = allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "6000"}, {"invoice": self.invoice_b.id, "amount": "4000"}])
        self.assertEqual(len(allocations), 2)
        self.assertEqual(self.payment.allocations.aggregate(total=Sum("amount"))["total"], Decimal("10000"))
        self.assertEqual(Invoice.objects.get(id=self.invoice_a.id).status, "paid")
        self.assertEqual(Invoice.objects.get(id=self.invoice_b.id).status, "paid")
        self.assertEqual(self.payment.unallocated_amount, Decimal("0"))

    def test_accepts_invoice_instance(self):
        allocation = allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a, "amount": "1000"}])[0]
        self.assertEqual(allocation.invoice_id, self.invoice_a.id)

    def test_rejects_payment_over_allocation(self):
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds payment amount"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "10001"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_invoice_over_allocation(self):
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds invoice remaining amount"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "6001"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_duplicate_invoice_entries(self):
        with self.assertRaisesMessage(ValidationError, "An invoice may only appear once in an allocation request"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "1000"}, {"invoice": self.invoice_a.id, "amount": "1000"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_cross_workspace_invoice(self):
        other_tenant = Tenant.objects.create(owner=self.other_owner, workspace=self.other_workspace, full_name="Other", phone="8888888888", permanent_address="Delhi")
        other_property = Property.objects.create(owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg", address="Other Address", city="Delhi", state="Delhi", pincode="110001")
        other_unit = Unit.objects.create(property=other_property, unit_type="room", unit_number="B-1", rent=Decimal("1000.00"))
        other_occupancy = Occupancy.objects.create(tenant=other_tenant, unit=other_unit, allotted_by=self.other_owner, rent=Decimal("1000.00"), check_in_date=date(2026, 1, 1), next_due_date=date(2026, 2, 1), billing_type="arrears", billing_cycle="monthly")
        other_invoice = Invoice.objects.create(occupancy=other_occupancy, billing_start=date(2026, 1, 1), billing_end=date(2026, 1, 31), rent_amount=Decimal("1000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 2, 5))
        with self.assertRaisesMessage(ValidationError, "One or more invoices were not found"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": other_invoice.id, "amount": "1000"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_cross_workspace_payment(self):
        other_payment = Payment.objects.create(workspace=self.other_workspace, invoice=None, amount=Decimal("1000"), payment_method="bank", payment_date=date(2026, 9, 6))
        with self.assertRaisesMessage(ValidationError, "Payment not found"):
            allocate_payment(None, self.workspace, other_payment, [{"invoice": self.invoice_a.id, "amount": "1000"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_empty_and_malformed_requests(self):
        with self.assertRaisesMessage(ValidationError, "At least one invoice allocation is required"):
            allocate_payment(None, self.workspace, self.payment, [])
        with self.assertRaisesMessage(ValidationError, "Invalid allocation entry"):
            allocate_payment(None, self.workspace, self.payment, [None])

    def test_rejects_invalid_ids_and_amounts(self):
        for invoice_id in (None, 0, -1, "bad"):
            with self.subTest(invoice_id=invoice_id), self.assertRaises(ValidationError):
                allocate_payment(None, self.workspace, self.payment, [{"invoice": invoice_id, "amount": "1000"}])
        for amount in ("0", "-1", "bad", "NaN", "Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": amount}])

    def test_rejects_missing_payment_and_invoice(self):
        with self.assertRaisesMessage(ValidationError, "Payment not found"):
            allocate_payment(None, self.workspace, 999999, [{"invoice": self.invoice_a.id, "amount": "1000"}])
        with self.assertRaisesMessage(ValidationError, "One or more invoices were not found"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": 999999, "amount": "1000"}])

    def test_payment_capacity_accounts_for_existing_allocations(self):
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "6000"}])
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds payment amount"):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_b.id, "amount": "4001"}])
        self.assertEqual(self.payment.unallocated_amount, Decimal("4000"))
        self.assertEqual(PaymentAllocation.objects.count(), 1)

    def test_invoice_capacity_is_enforced_across_payments(self):
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "6000"}])
        second = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("1000"), payment_method="cash", payment_date=date(2026, 9, 6))
        with self.assertRaisesMessage(ValidationError, "Allocation exceeds invoice remaining amount"):
            allocate_payment(None, self.workspace, second, [{"invoice": self.invoice_a.id, "amount": "1"}])
        self.assertEqual(self.invoice_a.allocations.aggregate(total=Sum("amount"))["total"], Decimal("6000"))

    def test_incremental_allocation_reaches_exact_boundaries(self):
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "2500"}])
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a, "amount": "3500"}])
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.paid_amount, Decimal("6000"))
        self.assertEqual(self.invoice_a.status, "paid")
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_b.id, "amount": "4000"}])
        self.assertEqual(self.payment.unallocated_amount, Decimal("0"))

    def test_multi_invoice_partial_allocation_updates_each_invoice(self):
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "3000"}, {"invoice": self.invoice_b.id, "amount": "2000"}])
        self.invoice_a.refresh_from_db()
        self.invoice_b.refresh_from_db()
        self.assertEqual(self.invoice_a.paid_amount, Decimal("3000"))
        self.assertEqual(self.invoice_a.status, "partial")
        self.assertEqual(self.invoice_b.paid_amount, Decimal("2000"))
        self.assertEqual(self.invoice_b.status, "partial")
        self.assertEqual(self.payment.unallocated_amount, Decimal("5000"))

    def test_rejected_multi_invoice_request_is_atomic(self):
        with self.assertRaises(ValidationError):
            allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "1000"}, {"invoice": 999999, "amount": "1000"}])
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.paid_amount, Decimal("0"))
        self.assertEqual(self.invoice_a.status, "pending")

    def test_allocation_rows_are_immutable_after_creation(self):
        allocation = allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "1000"}])[0]
        allocation.amount = Decimal("2000")
        with self.assertRaisesMessage(ValidationError, "Payment allocation payment, invoice and amount cannot be changed after creation"):
            allocation.save()
        allocation.refresh_from_db()
        self.assertEqual(allocation.amount, Decimal("1000"))

    def test_payment_amount_and_invoice_remain_unchanged(self):
        allocate_payment(None, self.workspace, self.payment, [{"invoice": self.invoice_a.id, "amount": "1000"}])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("10000"))
        self.assertIsNone(self.payment.invoice_id)
