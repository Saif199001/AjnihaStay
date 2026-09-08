from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import User
from payments.adjustment_service import (
    calculate_invoice_financial_position,
    create_financial_adjustment,
)
from payments.models import FinancialAdjustment, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class FinancialAdjustmentServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("adjustment-service@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Adjustment Service Workspace",
            slug="adjustment-service-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Adjustment Service Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Adjustment Service Property",
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

    def create_adjustment(self, **overrides):
        data = {
            "invoice": self.invoice.id,
            "adjustment_type": FinancialAdjustment.TYPE_CREDIT,
            "amount": "1000.00",
            "reason": "Approved service issue credit",
            "reference": "CASE-123",
            "idempotency_key": "ADJ-CASE-123",
        }
        data.update(overrides)
        return create_financial_adjustment(self.owner, self.workspace, data)

    def create_payment(self, amount):
        payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            amount=Decimal(amount),
            payment_method="cash",
            payment_date=date(2026, 2, 1),
        )
        PaymentAllocation.objects.create(
            payment=payment,
            invoice=self.invoice,
            amount=Decimal(amount),
        )
        return payment

    def test_financial_position_starts_from_gross_receivable(self):
        position = calculate_invoice_financial_position(self.invoice)

        self.assertEqual(position["gross_receivable"], Decimal("10000.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("10000.00"))
        self.assertEqual(position["settlement"], Decimal("0"))
        self.assertEqual(position["outstanding"], Decimal("10000.00"))
        self.assertEqual(position["status"], "pending")

    def test_credit_reduces_collectible_balance_without_changing_payment_settlement(self):
        adjustment, position, created = self.create_adjustment()

        self.assertTrue(created)
        self.assertEqual(adjustment.amount, Decimal("1000.00"))
        self.assertEqual(position["credit_adjustments"], Decimal("1000.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("9000.00"))
        self.assertEqual(position["settlement"], Decimal("0"))
        self.assertEqual(position["outstanding"], Decimal("9000.00"))
        self.assertEqual(Invoice.objects.get(pk=self.invoice.pk).paid_amount, Decimal("0"))

    def test_debit_increases_collectible_balance(self):
        adjustment, position, created = self.create_adjustment(
            adjustment_type=FinancialAdjustment.TYPE_DEBIT,
            amount="2000.00",
            reason="Additional utility charge",
            idempotency_key="ADJ-DEBIT-1",
        )

        self.assertTrue(created)
        self.assertEqual(adjustment.adjustment_type, FinancialAdjustment.TYPE_DEBIT)
        self.assertEqual(position["debit_adjustments"], Decimal("2000.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("12000.00"))
        self.assertEqual(position["outstanding"], Decimal("12000.00"))

    def test_discount_waiver_and_write_off_are_credit_side_and_distinguishable(self):
        for index, adjustment_type in enumerate(
            (
                FinancialAdjustment.TYPE_DISCOUNT,
                FinancialAdjustment.TYPE_WAIVER,
                FinancialAdjustment.TYPE_WRITE_OFF,
            )
        ):
            self.create_adjustment(
                adjustment_type=adjustment_type,
                amount="100.00",
                reason=f"Approved {adjustment_type}",
                idempotency_key=f"ADJ-{adjustment_type}-{index}",
            )

        position = calculate_invoice_financial_position(self.invoice)
        self.assertEqual(position["credit_adjustments"], Decimal("300.00"))
        self.assertEqual(position["adjustment_totals"][FinancialAdjustment.TYPE_DISCOUNT], Decimal("100.00"))
        self.assertEqual(position["adjustment_totals"][FinancialAdjustment.TYPE_WAIVER], Decimal("100.00"))
        self.assertEqual(position["adjustment_totals"][FinancialAdjustment.TYPE_WRITE_OFF], Decimal("100.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("9700.00"))

    def test_partial_payment_then_credit_recalculates_outstanding_and_status(self):
        self.create_payment("5000.00")

        adjustment, position, created = self.create_adjustment(
            amount="1000.00",
            idempotency_key="ADJ-PARTIAL-CREDIT",
        )

        self.assertTrue(created)
        self.assertEqual(position["settlement"], Decimal("5000.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("9000.00"))
        self.assertEqual(position["outstanding"], Decimal("4000.00"))
        self.assertEqual(position["status"], "partial")
        self.assertEqual(Payment.objects.get(pk=self.invoice.payments.get().pk).amount, Decimal("5000.00"))

    def test_partial_payment_then_debit_increases_outstanding(self):
        self.create_payment("5000.00")

        _, position, _ = self.create_adjustment(
            adjustment_type=FinancialAdjustment.TYPE_DEBIT,
            amount="2000.00",
            reason="Additional utility charge",
            idempotency_key="ADJ-PARTIAL-DEBIT",
        )

        self.assertEqual(position["settlement"], Decimal("5000.00"))
        self.assertEqual(position["adjusted_receivable"], Decimal("12000.00"))
        self.assertEqual(position["outstanding"], Decimal("7000.00"))
        self.assertEqual(position["status"], "partial")

    def test_credit_cannot_exceed_remaining_collectible_balance(self):
        self.create_payment("9000.00")

        with self.assertRaisesMessage(ValidationError, "Adjustment exceeds remaining collectible balance"):
            self.create_adjustment(amount="2000.00", idempotency_key="ADJ-OVER")

        self.assertEqual(FinancialAdjustment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.filter(invoice=self.invoice).count(), 1)

    def test_credit_equal_to_remaining_balance_does_not_appear_as_cash_collection(self):
        self.create_payment("5000.00")
        _, position, _ = self.create_adjustment(
            amount="5000.00",
            idempotency_key="ADJ-ZERO-COLLECTIBLE",
        )

        self.assertEqual(position["adjusted_receivable"], Decimal("5000.00"))
        self.assertEqual(position["settlement"], Decimal("5000.00"))
        self.assertEqual(position["outstanding"], Decimal("0"))
        self.assertEqual(position["status"], "paid")
        self.assertEqual(Invoice.objects.get(pk=self.invoice.pk).paid_amount, Decimal("5000.00"))

    def test_credit_on_fully_settled_invoice_is_rejected(self):
        self.create_payment("10000.00")

        with self.assertRaisesMessage(ValidationError, "Adjustment exceeds remaining collectible balance"):
            self.create_adjustment(amount="1.00", idempotency_key="ADJ-FULLY-PAID")

    def test_zero_collectible_without_settlement_remains_pending(self):
        self.create_adjustment(
            amount="10000.00",
            idempotency_key="ADJ-WRITE-OFF-FULL",
            adjustment_type=FinancialAdjustment.TYPE_WRITE_OFF,
            reason="Approved full write-off",
        )

        position = calculate_invoice_financial_position(self.invoice)
        self.assertEqual(position["adjusted_receivable"], Decimal("0.00"))
        self.assertEqual(position["settlement"], Decimal("0"))
        self.assertEqual(position["outstanding"], Decimal("0"))
        self.assertEqual(position["status"], "pending")
        self.assertEqual(Invoice.objects.get(pk=self.invoice.pk).paid_amount, Decimal("0"))

    def test_idempotent_retry_returns_existing_adjustment(self):
        first, first_position, created = self.create_adjustment()
        second, second_position, created_again = self.create_adjustment()

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first_position["adjusted_receivable"], second_position["adjusted_receivable"])
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_idempotency_key_cannot_be_reused_for_different_operation(self):
        self.create_adjustment()

        with self.assertRaisesMessage(
            ValidationError,
            "Idempotency key already used for a different adjustment",
        ):
            self.create_adjustment(amount="1100.00")

        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_service_requires_manager_level_membership(self):
        staff = User.objects.create_user("adjustment-staff@example.com", "StrongPass123!")
        Membership.objects.create(
            workspace=self.workspace,
            user=staff,
            role=Membership.ROLE_STAFF,
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Financial adjustment mutation requires manager-level access",
        ):
            create_financial_adjustment(
                staff,
                self.workspace,
                {
                    "invoice": self.invoice.id,
                    "adjustment_type": "credit",
                    "amount": "100.00",
                    "reason": "Staff attempt",
                },
            )

    def test_cross_workspace_invoice_is_not_visible_to_service(self):
        other_owner = User.objects.create_user("adjustment-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Adjustment Service Workspace",
            slug="other-adjustment-service-workspace",
            owner=other_owner,
        )
        Membership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role=Membership.ROLE_OWNER,
        )

        with self.assertRaisesMessage(ValidationError, "Invoice not found"):
            create_financial_adjustment(
                self.owner,
                other_workspace,
                {
                    "invoice": self.invoice.id,
                    "adjustment_type": "credit",
                    "amount": "100.00",
                    "reason": "Cross workspace",
                },
            )
