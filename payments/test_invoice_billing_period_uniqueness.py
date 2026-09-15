from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .invoice_generation_service import generate_invoice_for_occupancy
from .models import Invoice


class InvoiceBillingPeriodUniquenessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("f3-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="F3 Workspace", slug="f3-workspace", owner=self.owner
        )
        Membership.objects.create(
            workspace=self.workspace, user=self.owner, role="owner"
        )
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="F3 Property",
            property_type="pg",
            address="Test Address",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="room",
            unit_number="F3-101",
            rent=Decimal("10000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="F3 Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            allotted_by=self.owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.period = {
            "billing_start": date(2026, 9, 1),
            "billing_end": date(2026, 10, 1),
            "due_date": date(2026, 10, 1),
        }

    def test_database_constraint_rejects_duplicate_invoice_period(self):
        Invoice.objects.create(
            occupancy=self.occupancy,
            rent_amount=Decimal("10000.00"),
            charges_amount=Decimal("0.00"),
            **self.period,
        )
        with self.assertRaises(IntegrityError):
            Invoice.objects.create(
                occupancy=self.occupancy,
                rent_amount=Decimal("10000.00"),
                charges_amount=Decimal("0.00"),
                **self.period,
            )

    def test_invoice_generation_is_idempotent_for_existing_period(self):
        first, created = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            self.occupancy.id,
            **self.period,
        )
        self.assertTrue(created)

        second, created = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            self.occupancy.id,
            **self.period,
        )
        self.assertFalse(created)
        self.assertEqual(second.id, first.id)
        self.assertEqual(
            Invoice.objects.filter(
                occupancy=self.occupancy,
                billing_start=self.period["billing_start"],
                billing_end=self.period["billing_end"],
            ).count(),
            1,
        )
