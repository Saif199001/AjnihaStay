from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import AdvanceCredit, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class AdvanceCreditPaymentCapacityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("credit-capacity-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Credit Capacity Workspace",
            slug="credit-capacity-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Credit Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Credit Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="C-1",
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
        self.payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("10000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 7),
        )

    def test_unallocated_amount_excludes_reserved_advance_credit(self):
        AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=self.payment,
            original_amount=Decimal("4000.00"),
        )

        self.assertEqual(self.payment.reserved_credit_amount, Decimal("4000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("6000.00"))

    def test_allocation_cannot_spend_reserved_credit(self):
        AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=self.payment,
            original_amount=Decimal("4000.00"),
        )

        allocation = allocate_payment(
            self.owner,
            self.workspace,
            self.payment,
            [{"invoice": self.invoice.id, "amount": "6000"}],
        )[0]
        self.assertEqual(allocation.amount, Decimal("6000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("0.00"))

        with self.assertRaisesMessage(
            ValidationError,
            "Allocation exceeds payment amount",
        ):
            allocate_payment(
                self.owner,
                self.workspace,
                self.payment,
                [{"invoice": self.invoice.id, "amount": "1"}],
            )

        self.assertEqual(
            PaymentAllocation.objects.filter(payment=self.payment).count(),
            1,
        )

    def test_reserved_credit_does_not_reduce_invoice_by_itself(self):
        AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=self.payment,
            original_amount=Decimal("4000.00"),
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")
        self.assertEqual(self.invoice.due_amount, Decimal("10000.00"))

    def test_capacity_is_restored_only_by_releasing_credit_in_later_phase(self):
        credit = AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=self.payment,
            original_amount=Decimal("4000.00"),
        )
        self.assertEqual(credit.available_amount, Decimal("4000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("6000.00"))
