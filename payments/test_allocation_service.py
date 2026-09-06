from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from payments.allocation_service import allocate_payment
from payments.models import Invoice, Payment, PaymentAllocation
from tenant.models import Occupancy, Property, Tenant, Unit
from workspaces.models import Workspace


class PaymentAllocationServiceTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Allocation Workspace")
        self.other_workspace = Workspace.objects.create(name="Other Workspace")
        self.tenant = Tenant.objects.create(workspace=self.workspace, full_name="Tenant One")
        self.property = Property.objects.create(workspace=self.workspace, name="Property One")
        self.unit = Unit.objects.create(property=self.property, unit_number="A-1")
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            start_date="2026-01-01",
            rent_amount=Decimal("10000"),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        self.invoice_a = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start="2026-01-01",
            billing_end="2026-01-31",
            rent_amount=Decimal("6000"),
            charges_amount=0,
            due_date="2026-02-05",
        )
        self.invoice_b = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start="2026-02-01",
            billing_end="2026-02-28",
            rent_amount=Decimal("4000"),
            charges_amount=0,
            due_date="2026-03-05",
        )
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000"),
            payment_method="bank",
            payment_date="2026-09-06",
        )

    def test_allocates_one_payment_across_multiple_invoices(self):
        allocations = allocate_payment(
            None,
            self.workspace,
            self.payment,
            [
                {"invoice": self.invoice_a.id, "amount": Decimal("6000")},
                {"invoice": self.invoice_b.id, "amount": Decimal("4000")},
            ],
        )

        self.assertEqual(len(allocations), 2)
        self.assertEqual(self.payment.allocations.aggregate(total=__import__("django").db.models.Sum("amount"))["total"], Decimal("10000"))
        self.assertEqual(Invoice.objects.get(id=self.invoice_a.id).status, "paid")
        self.assertEqual(Invoice.objects.get(id=self.invoice_b.id).status, "paid")

    def test_rejects_payment_over_allocation(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice_a.id, "amount": Decimal("10001")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_invoice_over_allocation(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice_a.id, "amount": Decimal("6001")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rejects_duplicate_invoice_entries(self):
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [
                    {"invoice": self.invoice_a.id, "amount": Decimal("1000")},
                    {"invoice": self.invoice_a.id, "amount": Decimal("1000")},
                ],
            )

    def test_rejects_cross_workspace_invoice(self):
        other_tenant = Tenant.objects.create(workspace=self.other_workspace, full_name="Other")
        other_property = Property.objects.create(workspace=self.other_workspace, name="Other Property")
        other_unit = Unit.objects.create(property=other_property, unit_number="B-1")
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            start_date="2026-01-01",
            rent_amount=Decimal("1000"),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        other_invoice = Invoice.objects.create(
            occupancy=other_occupancy,
            billing_start="2026-01-01",
            billing_end="2026-01-31",
            rent_amount=Decimal("1000"),
            charges_amount=0,
            due_date="2026-02-05",
        )
        with self.assertRaises(ValidationError):
            allocate_payment(
                None,
                self.workspace,
                self.payment,
                [{"invoice": other_invoice.id, "amount": Decimal("1000")}],
            )
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_partial_allocation_updates_invoice_state(self):
        allocate_payment(
            None,
            self.workspace,
            self.payment,
            [{"invoice": self.invoice_a.id, "amount": Decimal("2500")}],
        )
        invoice = Invoice.objects.get(id=self.invoice_a.id)
        self.assertEqual(invoice.paid_amount, Decimal("2500"))
        self.assertEqual(invoice.status, "partial")
        self.assertEqual(self.payment.unallocated_amount, Decimal("7500"))
