from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.db.models import Sum
from django.test import TransactionTestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(
            "allocation-concurrency@example.com", "StrongPass123!"
        )
        self.workspace = Workspace.objects.create(
            name="Allocation Concurrency Workspace",
            slug="allocation-concurrency-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner"
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Concurrency Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Concurrency Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="C-1",
            rent=Decimal("10000.00"),
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        self.invoice_a = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("6000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.invoice_b = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 2, 1),
            billing_end=date(2026, 2, 28),
            rent_amount=Decimal("6000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 3, 5),
        )

    def _payment(self, amount):
        return Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal(amount),
            payment_method="bank",
            payment_date=date(2026, 9, 7),
        )

    def _run_allocation(self, payment_id, allocations):
        close_old_connections()
        try:
            payment = Payment.objects.get(id=payment_id)
            return (
                "success",
                allocate_payment(
                    self.owner,
                    self.workspace,
                    payment,
                    allocations,
                ),
            )
        except ValidationError as exc:
            return ("rejected", str(exc))
        finally:
            close_old_connections()

    def test_concurrent_allocations_cannot_over_allocate_same_payment(self):
        payment = self._payment("10000")
        barrier_allocations = [
            {"invoice": self.invoice_a.id, "amount": "6000"},
        ]
        second_allocations = [
            {"invoice": self.invoice_b.id, "amount": "5000"},
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._run_allocation,
                    payment.id,
                    barrier_allocations,
                ),
                executor.submit(
                    self._run_allocation,
                    payment.id,
                    second_allocations,
                ),
            ]
            results = [future.result(timeout=15) for future in futures]

        successful = [result for result in results if result[0] == "success"]
        rejected = [result for result in results if result[0] == "rejected"]
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(rejected), 1)

        payment.refresh_from_db()
        allocated = PaymentAllocation.objects.filter(payment=payment).aggregate(
            total=Sum("amount")
        )["total"]
        self.assertEqual(allocated, Decimal("6000"))
        self.assertLessEqual(allocated, payment.amount)

    def test_concurrent_allocations_cannot_over_allocate_same_invoice(self):
        first_payment = self._payment("6000")
        second_payment = self._payment("6000")
        allocations = [{"invoice": self.invoice_a.id, "amount": "6000"}]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._run_allocation,
                    first_payment.id,
                    allocations,
                ),
                executor.submit(
                    self._run_allocation,
                    second_payment.id,
                    allocations,
                ),
            ]
            results = [future.result(timeout=15) for future in futures]

        successful = [result for result in results if result[0] == "success"]
        rejected = [result for result in results if result[0] == "rejected"]
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(rejected), 1)

        invoice = Invoice.objects.get(id=self.invoice_a.id)
        allocated = PaymentAllocation.objects.filter(invoice=invoice).aggregate(
            total=Sum("amount")
        )["total"]
        self.assertEqual(allocated, Decimal("6000"))
        self.assertEqual(invoice.paid_amount, Decimal("6000"))
        self.assertEqual(invoice.status, "paid")

    def test_concurrent_multi_invoice_allocations_use_deterministic_lock_order(self):
        first_payment = self._payment("12000")
        second_payment = self._payment("12000")

        # Submit opposite invoice orders. The service must normalize and lock
        # affected invoices by ascending ID, so neither transaction can form a
        # circular wait on invoice locks.
        first_request = [
            {"invoice": self.invoice_a.id, "amount": "3000"},
            {"invoice": self.invoice_b.id, "amount": "3000"},
        ]
        second_request = [
            {"invoice": self.invoice_b.id, "amount": "3000"},
            {"invoice": self.invoice_a.id, "amount": "3000"},
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._run_allocation,
                    first_payment.id,
                    first_request,
                ),
                executor.submit(
                    self._run_allocation,
                    second_payment.id,
                    second_request,
                ),
            ]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual([result[0] for result in results].count("success"), 2)

        invoice_a = Invoice.objects.get(id=self.invoice_a.id)
        invoice_b = Invoice.objects.get(id=self.invoice_b.id)
        self.assertEqual(invoice_a.paid_amount, Decimal("6000"))
        self.assertEqual(invoice_b.paid_amount, Decimal("6000"))
        self.assertEqual(invoice_a.status, "paid")
        self.assertEqual(invoice_b.status, "paid")
        self.assertEqual(
            PaymentAllocation.objects.filter(invoice=invoice_a).aggregate(
                total=Sum("amount")
            )["total"],
            Decimal("6000"),
        )
        self.assertEqual(
            PaymentAllocation.objects.filter(invoice=invoice_b).aggregate(
                total=Sum("amount")
            )["total"],
            Decimal("6000"),
        )
