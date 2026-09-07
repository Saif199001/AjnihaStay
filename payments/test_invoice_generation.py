from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Charge, Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .invoice_generation_service import generate_invoice_for_occupancy
from .models import Invoice, Payment, PaymentAllocation


class InvoiceGenerationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("invoice-generation-owner@example.com", "StrongPass123!")
        self.other = User.objects.create_user("invoice-generation-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Invoice Generation Workspace", slug="invoice-generation-workspace", owner=self.owner
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Invoice Generation Workspace", slug="other-invoice-generation-workspace", owner=self.other
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")

        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Invoice Generation Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="701",
            rent=Decimal("12000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Invoice Generation Tenant",
            phone="8888888888",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("12000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        Charge.objects.create(
            occupancy=self.occupancy,
            charge_type="electricity",
            description="September electricity",
            amount=Decimal("850.00"),
            charge_date=date(2026, 9, 15),
        )
        Charge.objects.create(
            occupancy=self.occupancy,
            charge_type="food",
            description="October food",
            amount=Decimal("500.00"),
            charge_date=date(2026, 10, 1),
        )

    def test_generates_invoice_from_rent_and_period_charges(self):
        invoice, created = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            self.occupancy,
            date(2026, 9, 1),
            date(2026, 10, 1),
        )

        self.assertTrue(created)
        self.assertEqual(invoice.rent_amount, Decimal("12000.00"))
        self.assertEqual(invoice.charges_amount, Decimal("850.00"))
        self.assertEqual(invoice.total_amount, Decimal("12850.00"))
        self.assertEqual(invoice.due_date, date(2026, 9, 1))
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_generation_is_idempotent_for_same_billing_period(self):
        first, first_created = generate_invoice_for_occupancy(
            self.owner, self.workspace, self.occupancy,
            date(2026, 9, 1), date(2026, 10, 1), date(2026, 9, 5),
        )
        second, second_created = generate_invoice_for_occupancy(
            self.owner, self.workspace, self.occupancy,
            date(2026, 9, 1), date(2026, 10, 1), date(2026, 9, 20),
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.due_date, date(2026, 9, 5))
        self.assertEqual(Invoice.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_cross_workspace_occupancy_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Occupancy not found"):
            generate_invoice_for_occupancy(
                self.other,
                self.other_workspace,
                self.occupancy,
                date(2026, 9, 1),
                date(2026, 10, 1),
            )

    def test_inactive_occupancy_is_rejected(self):
        self.occupancy.is_active = False
        self.occupancy.save()

        with self.assertRaisesMessage(ValidationError, "Inactive occupancy cannot generate an invoice"):
            generate_invoice_for_occupancy(
                self.owner,
                self.workspace,
                self.occupancy,
                date(2026, 9, 1),
                date(2026, 10, 1),
            )

    def test_billing_start_before_check_in_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Billing start date cannot be before occupancy check-in date"):
            generate_invoice_for_occupancy(
                self.owner,
                self.workspace,
                self.occupancy,
                date(2026, 8, 31),
                date(2026, 10, 1),
            )

    def test_invalid_billing_period_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Billing end date must be after billing start date"):
            generate_invoice_for_occupancy(
                self.owner,
                self.workspace,
                self.occupancy,
                date(2026, 10, 1),
                date(2026, 10, 1),
            )

    def test_billing_end_after_check_out_is_rejected(self):
        self.occupancy.check_out_date = date(2026, 9, 30)
        self.occupancy.save()

        with self.assertRaisesMessage(ValidationError, "Billing end date cannot be after occupancy check-out date"):
            generate_invoice_for_occupancy(
                self.owner,
                self.workspace,
                self.occupancy,
                date(2026, 9, 1),
                date(2026, 10, 1),
            )

    def test_generation_does_not_create_payment_or_allocation(self):
        invoice, _ = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            self.occupancy,
            date(2026, 9, 1),
            date(2026, 10, 1),
        )

        self.assertIsNotNone(invoice.pk)
        self.assertEqual(invoice.allocations.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
