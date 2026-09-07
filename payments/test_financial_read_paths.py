from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from .models import Invoice, Payment, PaymentAllocation
from .services import calculate_final_settlement, recalculate_invoice_state


class AllocationAwareFinancialReadTests(TestCase):
    def setUp(self):
        password = "StrongPass123!"
        self.owner = User.objects.create_user("read-owner@example.com", password)
        self.workspace = Workspace.objects.create(
            name="Read Workspace", slug="read-workspace", owner=self.owner
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner"
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Read Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="401",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Read Tenant",
            phone="8888888888",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
            security_deposit=Decimal("2000.00"),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 10, 1),
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("500.00"),
            due_date=date(2026, 10, 1),
        )

    def make_payment(self, amount):
        return Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal(amount),
            payment_method="upi",
            payment_date=date(2026, 9, 3),
        )

    def test_invoice_recalculation_uses_allocations_as_canonical_paid_amount(self):
        payment = self.make_payment("4000.00")
        PaymentAllocation.objects.create(
            payment=payment,
            invoice=self.invoice,
            amount=Decimal("4000.00"),
        )
        self.invoice.paid_amount = Decimal("0.00")
        self.invoice.status = "pending"
        Invoice.objects.filter(id=self.invoice.id).update(
            paid_amount=Decimal("0.00"), status="pending"
        )

        recalculate_invoice_state(self.invoice)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("4000.00"))
        self.assertEqual(self.invoice.status, "partial")

    def test_settlement_uses_allocations_not_payment_amount(self):
        payment = self.make_payment("6000.00")
        PaymentAllocation.objects.create(
            payment=payment,
            invoice=self.invoice,
            amount=Decimal("2500.00"),
        )

        result = calculate_final_settlement(self.occupancy.id, self.workspace)

        self.assertEqual(result["total_paid"], Decimal("2500.00"))
        self.assertEqual(result["total_due"], Decimal("8000.00"))
        self.assertEqual(result["final_balance"], Decimal("6000.00"))
