from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from payments.invoice_generation_service import generate_invoice_for_occupancy
from payments.ledger_models import FinancialLedgerEntry
from payments.models import Payment
from payments.refund_models import PaymentRefund
from payments.refund_service import request_payment_refund, transition_payment_refund
from payments.services import record_payment
from properties.services import create_property
from tenant.services import create_occupancy, create_tenant
from unit.services import create_unit


class PaymentRefundMutationBoundaryTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "refund-boundary-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Refund Boundary Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Refund Boundary Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )
        self.unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )
        self.tenant = create_tenant(
            self.owner,
            self.workspace,
            {
                "full_name": "Refund Tenant",
                "phone": "9876543210",
                "permanent_address": "Test Address",
            },
            MultiValueDict(),
        )
        self.occupancy = create_occupancy(
            self.owner,
            self.workspace,
            {
                "tenant": self.tenant.pk,
                "unit": self.unit.pk,
                "rent": Decimal("10000"),
                "billing_type": "advance",
                "billing_cycle": "monthly",
                "check_in_date": date(2026, 10, 1),
                "check_out_date": None,
                "next_due_date": date(2026, 11, 1),
                "security_deposit": Decimal("10000"),
                "deposit_paid": False,
            },
        )
        self.invoice, _ = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            self.occupancy,
            date(2026, 10, 1),
            date(2026, 11, 1),
            date(2026, 10, 5),
        )
        self.payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.pk,
                "amount": Decimal("5000"),
                "payment_method": "cash",
                "payment_date": date(2026, 10, 5),
                "reference_id": "REFUND-BOUNDARY-PAYMENT",
                "notes": "",
            },
        )

    def refund_kwargs(self):
        return {
            "user": self.owner,
            "workspace": self.workspace,
            "payment": self.payment,
            "amount": Decimal("1000"),
            "reason": "Customer refund",
            "reference": "REF-1000",
            "idempotency_key": "refund-boundary-1000",
        }

    def test_direct_create_is_blocked(self):
        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment refund creation must be performed through the canonical refund service.",
        ):
            PaymentRefund.objects.create(
                workspace=self.workspace,
                payment=self.payment,
                amount=Decimal("1000"),
                status=PaymentRefund.STATUS_REQUESTED,
                reason="Direct refund",
                requested_by=self.owner,
            )

    def test_bulk_create_is_blocked(self):
        refund = PaymentRefund(
            workspace=self.workspace,
            payment=self.payment,
            amount=Decimal("1000"),
            status=PaymentRefund.STATUS_REQUESTED,
            reason="Bulk refund",
            requested_by=self.owner,
        )
        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment refund creation must be performed through the canonical refund service.",
        ):
            PaymentRefund.objects.bulk_create([refund])

    def test_direct_delete_and_queryset_delete_are_blocked(self):
        refund = request_payment_refund(**self.refund_kwargs())

        with self.assertRaisesMessage(PermissionDenied, "Payment refunds cannot be deleted."):
            refund.delete()

        with self.assertRaisesMessage(PermissionDenied, "Payment refunds cannot be deleted."):
            PaymentRefund.objects.filter(pk=refund.pk).delete()

    def test_queryset_update_and_bulk_update_are_blocked(self):
        refund = request_payment_refund(**self.refund_kwargs())

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment refunds must be mutated through the canonical refund service.",
        ):
            PaymentRefund.objects.filter(pk=refund.pk).update(status=PaymentRefund.STATUS_PROCESSING)

        refund.status = PaymentRefund.STATUS_PROCESSING
        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment refunds must be mutated through the canonical refund service.",
        ):
            PaymentRefund.objects.bulk_update([refund], ["status"])

    def test_direct_status_save_is_blocked(self):
        refund = request_payment_refund(**self.refund_kwargs())
        refund.status = PaymentRefund.STATUS_PROCESSING

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment refund status changes must be performed through the canonical refund service.",
        ):
            refund.save()

    def test_canonical_request_and_transition_work_and_post_ledger_events(self):
        refund = request_payment_refund(**self.refund_kwargs())
        self.assertEqual(refund.status, PaymentRefund.STATUS_REQUESTED)
        self.assertTrue(
            FinancialLedgerEntry.objects.filter(
                workspace=self.workspace,
                event_key=f"refund:{refund.pk}:requested",
            ).exists()
        )

        refund = transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status=PaymentRefund.STATUS_PROCESSING,
        )
        self.assertEqual(refund.status, PaymentRefund.STATUS_PROCESSING)

        refund = transition_payment_refund(
            user=self.owner,
            workspace=self.workspace,
            refund=refund,
            status=PaymentRefund.STATUS_SUCCEEDED,
        )
        self.assertEqual(refund.status, PaymentRefund.STATUS_SUCCEEDED)
        self.assertTrue(
            FinancialLedgerEntry.objects.filter(
                workspace=self.workspace,
                event_key=f"refund:{refund.pk}:succeeded",
            ).exists()
        )

    def test_failed_transition_requires_failure_reason(self):
        refund = request_payment_refund(**self.refund_kwargs())

        with self.assertRaisesMessage(
            ValidationError,
            "Refund failure reason is required",
        ):
            transition_payment_refund(
                user=self.owner,
                workspace=self.workspace,
                refund=refund,
                status=PaymentRefund.STATUS_FAILED,
            )
