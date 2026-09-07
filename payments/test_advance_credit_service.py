from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.advance_credit_service import create_advance_credit
from payments.models import AdvanceCredit, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class AdvanceCreditCreationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("advance-credit-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Advance Credit Workspace",
            slug="advance-credit-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Advance Credit Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Advance Credit Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="AC-1",
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

    def test_creates_credit_from_unallocated_payment_capacity(self):
        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "occupancy": self.occupancy.id,
                "amount": "4000",
            },
        )

        self.assertEqual(credit.original_amount, Decimal("4000.00"))
        self.assertEqual(credit.source_payment_id, self.payment.id)
        self.assertEqual(credit.tenant_id, self.tenant.id)
        self.assertEqual(credit.occupancy_id, self.occupancy.id)
        self.assertEqual(self.payment.unallocated_amount, Decimal("6000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.status, "pending")

    def test_credit_can_be_created_without_occupancy(self):
        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "amount": "2500",
            },
        )

        self.assertEqual(credit.occupancy_id, None)
        self.assertEqual(credit.available_amount, Decimal("2500.00"))

    def test_credit_amount_cannot_exceed_available_payment_capacity(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit exceeds available payment capacity",
        ):
            create_advance_credit(
                self.owner,
                self.workspace,
                {
                    "source_payment": self.payment.id,
                    "tenant": self.tenant.id,
                    "amount": "10000.01",
                },
            )

        self.assertFalse(AdvanceCredit.objects.filter(source_payment=self.payment).exists())

    def test_existing_payment_allocation_reduces_credit_capacity(self):
        PaymentAllocation.objects.create(
            payment=self.payment,
            invoice=self.invoice,
            amount=Decimal("6000.00"),
        )

        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "amount": "4000",
            },
        )

        self.assertEqual(credit.original_amount, Decimal("4000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("0.00"))

    def test_source_payment_cannot_create_second_credit(self):
        create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "amount": "4000",
            },
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit already exists for this source payment",
        ):
            create_advance_credit(
                self.owner,
                self.workspace,
                {
                    "source_payment": self.payment.id,
                    "tenant": self.tenant.id,
                    "amount": "1000",
                },
            )

    def test_payment_must_belong_to_workspace(self):
        other_owner = User.objects.create_user("other-owner@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Workspace",
            slug="other-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner")

        with self.assertRaisesMessage(ValidationError, "Payment not found"):
            create_advance_credit(
                self.owner,
                other_workspace,
                {
                    "source_payment": self.payment.id,
                    "tenant": self.tenant.id,
                    "amount": "1000",
                },
            )

    def test_tenant_must_belong_to_workspace(self):
        other_owner = User.objects.create_user("tenant-owner@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Tenant Workspace",
            slug="tenant-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner")
        other_tenant = Tenant.objects.create(
            owner=other_owner,
            workspace=other_workspace,
            full_name="Other Tenant",
            phone="8888888888",
            permanent_address="Noida",
        )

        with self.assertRaisesMessage(ValidationError, "Tenant not found"):
            create_advance_credit(
                self.owner,
                self.workspace,
                {
                    "source_payment": self.payment.id,
                    "tenant": other_tenant.id,
                    "amount": "1000",
                },
            )

    def test_occupancy_must_belong_to_selected_tenant(self):
        other_tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Other Workspace Tenant",
            phone="7777777777",
            permanent_address="Gurgaon",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit occupancy must belong to the selected tenant",
        ):
            create_advance_credit(
                self.owner,
                self.workspace,
                {
                    "source_payment": self.payment.id,
                    "tenant": other_tenant.id,
                    "occupancy": self.occupancy.id,
                    "amount": "1000",
                },
            )

    def test_payment_invoice_tenant_must_match_selected_credit_tenant(self):
        linked_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            amount=Decimal("5000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 7),
        )
        other_tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Mismatch Tenant",
            phone="6666666666",
            permanent_address="Faridabad",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit tenant must match the payment invoice tenant",
        ):
            create_advance_credit(
                self.owner,
                self.workspace,
                {
                    "source_payment": linked_payment.id,
                    "tenant": other_tenant.id,
                    "amount": "1000",
                },
            )

    def test_invalid_or_non_positive_amount_is_rejected(self):
        for amount in ("0", "-1", "not-a-number"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    create_advance_credit(
                        self.owner,
                        self.workspace,
                        {
                            "source_payment": self.payment.id,
                            "tenant": self.tenant.id,
                            "amount": amount,
                        },
                    )

    def test_full_capacity_can_be_reserved_once(self):
        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": self.payment.id,
                "tenant": self.tenant.id,
                "amount": "10000",
            },
        )

        self.assertEqual(credit.available_amount, Decimal("10000.00"))
        self.assertEqual(self.payment.unallocated_amount, Decimal("0.00"))
