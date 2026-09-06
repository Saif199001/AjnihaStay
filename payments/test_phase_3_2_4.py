from datetime import date
from decimal import Decimal
from threading import Barrier, Thread

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.db.models import Sum
from django.test import TransactionTestCase

from accounts.models import User
from payments.models import Invoice, Payment
from payments.services import record_payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class CanonicalFinancialConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user("concurrency@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Concurrency Workspace",
            slug="concurrency-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Concurrency Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="C-101",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Concurrency Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 1),
        )

    def _payment_data(self, amount):
        return {
            "invoice": self.invoice.id,
            "amount": Decimal(amount),
            "payment_method": "upi",
            "payment_date": date(2026, 9, 6),
        }

    def test_concurrent_payments_cannot_over_allocate_invoice(self):
        barrier = Barrier(2)
        outcomes = []

        def attempt(amount):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                record_payment(self.owner, self.workspace, self._payment_data(amount))
                outcomes.append("success")
            except ValidationError:
                outcomes.append("rejected")
            finally:
                close_old_connections()

        first = Thread(target=attempt, args=("6000.00",))
        second = Thread(target=attempt, args=("5000.00",))
        first.start()
        second.start()
        first.join(timeout=20)
        second.join(timeout=20)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(sorted(outcomes), ["rejected", "success"])

        self.invoice.refresh_from_db()
        total_paid = Payment.objects.filter(invoice=self.invoice).aggregate(total=Sum("amount"))["total"]
        self.assertEqual(total_paid, Decimal("6000.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("6000.00"))
        self.assertEqual(self.invoice.status, "partial")
