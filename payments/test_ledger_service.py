from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .ledger_models import FinancialLedgerEntry
from .ledger_service import post_ledger_event
from .models import Invoice, Payment, PaymentAllocation
from .services import create_invoice, record_payment


class FinancialLedgerPostingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ledger-owner@example.com", "ledger-test-password")
        self.other_owner = User.objects.create_user("ledger-other@example.com", "ledger-test-password")
        self.staff = User.objects.create_user("ledger-staff@example.com", "ledger-test-password")

        self.workspace = Workspace.objects.create(
            name="Ledger Workspace", slug="ledger-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Ledger Workspace", slug="other-ledger-workspace", owner=self.other_owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="Ledger Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj, unit_type="room", unit_number="401", rent=Decimal("10000.00")
        )
        tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="Ledger Tenant",
            phone="9999999999", permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1), security_deposit=Decimal("5000.00"), deposit_paid=True,
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30),
            rent_amount=Decimal("10000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 9, 30),
        )
        self.occurred_at = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    def post(self, **overrides):
        data = {
            "event_type": "invoice_created",
            "event_key": "invoice:created:1",
            "occurred_at": self.occurred_at,
            "amount": Decimal("10000.00"),
            "invoice": self.invoice,
            "occupancy": self.occupancy,
            "metadata": {"invoice_id": self.invoice.id},
        }
        data.update(overrides)
        return post_ledger_event(self.owner, self.workspace, **data)

    def test_posts_immutable_event_without_mutating_invoice(self):
        before = (self.invoice.paid_amount, self.invoice.status, self.invoice.rent_amount)
        entry = self.post()
        self.invoice.refresh_from_db()
        after = (self.invoice.paid_amount, self.invoice.status, self.invoice.rent_amount)

        self.assertEqual(entry.event_type, "invoice_created")
        self.assertEqual(entry.amount, Decimal("10000.00"))
        self.assertEqual(before, after)
        self.assertEqual(FinancialLedgerEntry.objects.count(), 1)

    def test_same_event_key_same_effect_is_idempotent(self):
        first = self.post()
        second = self.post()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FinancialLedgerEntry.objects.count(), 1)

    def test_same_event_key_different_effect_is_conflict(self):
        self.post()
        with self.assertRaisesMessage(ValidationError, "Ledger event key already exists for a different financial event"):
            self.post(amount=Decimal("9000.00"))
        self.assertEqual(FinancialLedgerEntry.objects.count(), 1)

    def test_event_key_is_workspace_scoped(self):
        first = self.post()
        other_entry = post_ledger_event(
            self.other_owner,
            self.other_workspace,
            event_type="invoice_created",
            event_key=first.event_key,
            occurred_at=self.occurred_at,
            amount=Decimal("100.00"),
        )
        self.assertNotEqual(first.pk, other_entry.pk)
        self.assertEqual(FinancialLedgerEntry.objects.count(), 2)

    def test_cross_workspace_source_is_rejected(self):
        other_property = Property.objects.create(
            owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110002",
        )
        other_unit = Unit.objects.create(
            property=other_property, unit_type="room", unit_number="501", rent=Decimal("8000.00")
        )
        other_tenant = Tenant.objects.create(
            owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant",
            phone="8888888888", permanent_address="Delhi",
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant, unit=other_unit, allotted_by=self.other_owner, rent=Decimal("8000.00"),
            check_in_date=date(2026, 9, 1), check_out_date=date(2026, 9, 30),
            next_due_date=date(2026, 10, 1), security_deposit=Decimal("0.00"), deposit_paid=False,
        )
        with self.assertRaisesMessage(ValidationError, "Ledger references must belong to the same workspace"):
            self.post(occupancy=other_occupancy)

    def test_staff_cannot_post(self):
        with self.assertRaises(PermissionDenied):
            post_ledger_event(
                self.staff,
                self.workspace,
                event_type="invoice_created",
                event_key="invoice:created:staff",
                occurred_at=self.occurred_at,
                amount=Decimal("100.00"),
            )
        self.assertFalse(FinancialLedgerEntry.objects.exists())

    def test_invalid_event_type_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Unsupported ledger event type"):
            self.post(event_type="unknown_event")

    def test_invalid_money_precision_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Ledger amount must use at most two decimal places"):
            self.post(amount=Decimal("10.001"))

    def test_existing_ledger_event_is_immutable(self):
        entry = self.post()
        entry.amount = Decimal("9000.00")
        with self.assertRaisesMessage(ValidationError, "Financial ledger entries cannot be changed after creation"):
            entry.save()

    def test_outer_transaction_rollback_removes_ledger_post(self):
        try:
            with transaction.atomic():
                self.post(event_key="invoice:created:rollback")
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        self.assertFalse(FinancialLedgerEntry.objects.filter(event_key="invoice:created:rollback").exists())

    def test_create_invoice_posts_ledger_event(self):
        invoice = create_invoice(
            self.owner,
            self.workspace,
            {
                "occupancy": self.occupancy.id,
                "billing_start": date(2026, 10, 1),
                "billing_end": date(2026, 10, 31),
                "rent_amount": "10000.00",
                "charges_amount": "500.00",
                "due_date": date(2026, 10, 31),
            },
        )
        entry = FinancialLedgerEntry.objects.get(event_key=f"invoice:{invoice.pk}:created")
        self.assertEqual(entry.event_type, "invoice_created")
        self.assertEqual(entry.amount, Decimal("10500.00"))
        self.assertEqual(entry.invoice_id, invoice.pk)
        self.assertEqual(entry.occupancy_id, self.occupancy.pk)

    def test_record_payment_posts_payment_and_allocation_events(self):
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": self.invoice.id,
                "amount": "10000.00",
                "payment_method": "upi",
                "payment_date": date(2026, 9, 30),
                "reference_id": "LEDGER-PAY-1",
            },
        )
        allocation = PaymentAllocation.objects.get(payment=payment)
        payment_entry = FinancialLedgerEntry.objects.get(event_key=f"payment:{payment.pk}:recorded")
        allocation_entry = FinancialLedgerEntry.objects.get(
            event_key=f"payment-allocation:{allocation.pk}:created"
        )
        self.assertEqual(payment_entry.event_type, "payment_recorded")
        self.assertEqual(payment_entry.amount, Decimal("10000.00"))
        self.assertEqual(payment_entry.payment_id, payment.pk)
        self.assertEqual(allocation_entry.event_type, "payment_allocated")
        self.assertEqual(allocation_entry.amount, Decimal("10000.00"))
        self.assertEqual(allocation_entry.payment_id, payment.pk)
        self.assertEqual(allocation_entry.invoice_id, self.invoice.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(Payment.objects.count(), 1)

    def test_payment_and_ledger_rollback_together(self):
        original_post = post_ledger_event

        def failing_post(*args, **kwargs):
            if kwargs.get("event_type") == "payment_recorded":
                raise RuntimeError("forced ledger failure")
            return original_post(*args, **kwargs)

        import payments.services as services_module
        services_module.post_ledger_event = failing_post
        try:
            with self.assertRaises(RuntimeError):
                record_payment(
                    self.owner,
                    self.workspace,
                    {
                        "invoice": self.invoice.id,
                        "amount": "1000.00",
                        "payment_method": "cash",
                        "payment_date": date(2026, 9, 30),
                    },
                )
        finally:
            services_module.post_ledger_event = original_post

        self.assertFalse(Payment.objects.exists())
        self.assertFalse(FinancialLedgerEntry.objects.exists())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "pending")
