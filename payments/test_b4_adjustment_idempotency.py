from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.db import close_old_connections

from accounts.models import User
from payments.adjustment_service import create_financial_adjustment
from payments.models import FinancialAdjustment, Invoice
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class FinancialAdjustmentIdempotencyRaceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user("b4-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="B4 Workspace",
            slug="b4-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=Membership.ROLE_OWNER,
        )

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="B4 Property",
            property_type="pg",
            address="B4 Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="B4-101",
            rent=Decimal("10000.00"),
            capacity=2,
        )

        self.tenants = []
        self.invoices = []
        for index in range(2):
            tenant = Tenant.objects.create(
                owner=self.owner,
                workspace=self.workspace,
                full_name=f"B4 Tenant {index + 1}",
                phone=f"900000000{index + 1}",
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
            invoice = Invoice.objects.create(
                occupancy=occupancy,
                billing_start=date(2026, 9, 1),
                billing_end=date(2026, 10, 1),
                rent_amount=Decimal("10000.00"),
                charges_amount=Decimal("0.00"),
                due_date=date(2026, 10, 1),
            )
            self.tenants.append(tenant)
            self.invoices.append(invoice)

    def _run_adjustment(self, invoice_id, barrier):
        close_old_connections()
        try:
            barrier.wait()
            return create_financial_adjustment(
                self.owner,
                self.workspace,
                {
                    "invoice": invoice_id,
                    "adjustment_type": FinancialAdjustment.TYPE_CREDIT,
                    "amount": Decimal("100.00"),
                    "reason": "B4 concurrent idempotency test",
                    "reference": "B4-RACE",
                    "idempotency_key": "b4-shared-key",
                },
            )
        finally:
            close_old_connections()

    def test_concurrent_same_key_on_different_invoices_is_deterministic(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self._run_adjustment, invoice.id, barrier)
                for invoice in self.invoices
            ]
            results = []
            errors = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append(exc)

        self.assertEqual(errors, [])
        self.assertEqual(FinancialAdjustment.objects.filter(
            workspace=self.workspace,
            idempotency_key="b4-shared-key",
        ).count(), 1)
        self.assertEqual(sum(created for _, _, created in results), 1)
        self.assertEqual(sum(not created for _, _, created in results), 1)

        existing = FinancialAdjustment.objects.get(
            workspace=self.workspace,
            idempotency_key="b4-shared-key",
        )
        self.assertEqual(existing.amount, Decimal("100.00"))
        self.assertEqual(existing.reference, "B4-RACE")

    def test_reusing_key_with_different_payload_is_rejected(self):
        adjustment, _, created = create_financial_adjustment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoices[0].id,
                "adjustment_type": FinancialAdjustment.TYPE_CREDIT,
                "amount": Decimal("100.00"),
                "reason": "Original B4 operation",
                "reference": "B4-ORIGINAL",
                "idempotency_key": "b4-payload-key",
            },
        )
        self.assertTrue(created)
        self.assertIsNotNone(adjustment.pk)

        with self.assertRaisesMessage(
            ValidationError,
            "Idempotency key already used for a different adjustment",
        ):
            create_financial_adjustment(
                self.owner,
                self.workspace,
                {
                    "invoice": self.invoices[1].id,
                    "adjustment_type": FinancialAdjustment.TYPE_CREDIT,
                    "amount": Decimal("200.00"),
                    "reason": "Different B4 operation",
                    "reference": "B4-DIFFERENT",
                    "idempotency_key": "b4-payload-key",
                },
            )
