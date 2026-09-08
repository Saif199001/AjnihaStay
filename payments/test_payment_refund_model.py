from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice, Payment
from payments.refund_models import PaymentRefund
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentRefundModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("refund-model@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Refund Model Workspace",
            slug="refund-model-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Refund Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Refund Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="R-1",
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
            invoice=self.invoice,
            amount=Decimal("1000.00"),
            payment_method="cash",
            payment_date=date(2026, 1, 10),
            reference_id="PAY-REFUND-1",
        )

    def make_refund(self, **overrides):
        data = {
            "workspace": self.workspace,
            "payment": self.payment,
            "amount": Decimal("250.00"),
            "status": PaymentRefund.STATUS_REQUESTED,
            "reason": "Customer refund",
            "reference": "REF-001",
            "idempotency_key": "REFUND-001",
            "requested_by": self.owner,
        }
        data.update(overrides)
        return PaymentRefund.objects.create(**data)

    def test_valid_refund_persists_expected_fields(self):
        refund = self.make_refund()
        self.assertEqual(refund.amount, Decimal("250.00"))
        self.assertEqual(refund.status, PaymentRefund.STATUS_REQUESTED)
        self.assertEqual(refund.payment_id, self.payment.id)
        self.assertEqual(refund.workspace_id, self.workspace.id)
        self.assertEqual(refund.requested_by_id, self.owner.id)

    def test_non_positive_amount_is_rejected(self):
        refund = PaymentRefund(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("0.00"),
            reason="Invalid amount",
            requested_by=self.owner,
        )
        with self.assertRaisesMessage(ValidationError, "Refund amount must be greater than zero"):
            refund.full_clean()

    def test_blank_reason_is_rejected(self):
        refund = PaymentRefund(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("100.00"),
            reason="   ",
            requested_by=self.owner,
        )
        with self.assertRaisesMessage(ValidationError, "Refund reason is required"):
            refund.full_clean()

    def test_cross_workspace_payment_is_rejected(self):
        other_owner = User.objects.create_user("refund-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Refund Workspace",
            slug="other-refund-workspace",
            owner=other_owner,
        )
        refund = PaymentRefund(
            workspace=other_workspace,
            payment=self.payment,
            amount=Decimal("100.00"),
            reason="Cross workspace",
            requested_by=other_owner,
        )
        with self.assertRaisesMessage(
            ValidationError,
            "Refund and payment must belong to the same workspace",
        ):
            refund.full_clean()

    def test_financial_facts_are_immutable(self):
        refund = self.make_refund()
        refund.amount = Decimal("300.00")
        with self.assertRaisesMessage(
            ValidationError,
            "Payment refunds cannot change financial facts after creation",
        ):
            refund.save()

    def test_valid_state_transitions_are_allowed(self):
        refund = self.make_refund()
        refund.status = PaymentRefund.STATUS_PROCESSING
        refund.save()
        refund.status = PaymentRefund.STATUS_SUCCEEDED
        refund.save()
        self.assertEqual(refund.status, PaymentRefund.STATUS_SUCCEEDED)

    def test_invalid_state_transition_is_rejected(self):
        refund = self.make_refund(status=PaymentRefund.STATUS_SUCCEEDED)
        refund.status = PaymentRefund.STATUS_FAILED
        with self.assertRaisesMessage(ValidationError, "Invalid refund state transition"):
            refund.save()

    def test_idempotency_key_is_unique_within_workspace(self):
        self.make_refund()
        duplicate = PaymentRefund(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("100.00"),
            reason="Retry",
            idempotency_key="REFUND-001",
            requested_by=self.owner,
        )
        with self.assertRaises(IntegrityError):
            duplicate.save(force_insert=True)
