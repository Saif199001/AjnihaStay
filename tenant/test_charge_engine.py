from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice
from workspaces.models import Membership, Workspace
from properties.models import Property
from unit.models import Unit

from .charge_service import create_charge, create_prorated_charge, prorate_amount
from .models import Charge, Occupancy, Tenant


class ChargeEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("charge-engine@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Charge Engine Workspace",
            slug="charge-engine-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Charge Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="101",
            rent=Decimal("30000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Charge Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            allotted_by=self.owner,
            rent=Decimal("30000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=date(2026, 9, 1),
            billing_end=date(2026, 10, 1),
            rent_amount=Decimal("30000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 10, 1),
        )

    def test_create_charge_updates_active_invoice_atomically(self):
        charge = create_charge(
            self.owner,
            self.workspace,
            occupancy=self.occupancy,
            charge_type="maintenance",
            amount=Decimal("500.00"),
            charge_date=date(2026, 9, 10),
            description="Maintenance",
        )
        self.invoice.refresh_from_db()
        self.assertEqual(charge.amount, Decimal("500.00"))
        self.assertEqual(self.invoice.charges_amount, Decimal("500.00"))
        self.assertEqual(self.invoice.total_amount, Decimal("30500.00"))

    def test_create_charge_rejects_inactive_occupancy(self):
        self.occupancy.is_active = False
        self.occupancy.save(update_fields=["is_active"])
        with self.assertRaisesMessage(ValidationError, "Inactive occupancy cannot receive a charge"):
            create_charge(
                self.owner,
                self.workspace,
                occupancy=self.occupancy,
                charge_type="maintenance",
                amount=Decimal("100.00"),
                charge_date=date(2026, 9, 10),
            )
        self.assertFalse(Charge.objects.filter(occupancy=self.occupancy).exists())

    def test_prorate_amount_uses_inclusive_calendar_days(self):
        amount = prorate_amount(
            Decimal("30000.00"),
            date(2026, 9, 1),
            date(2026, 9, 30),
            date(2026, 9, 16),
        )
        self.assertEqual(amount, Decimal("15000.00"))

    def test_prorate_amount_returns_zero_when_periods_do_not_overlap(self):
        amount = prorate_amount(
            Decimal("30000.00"),
            date(2026, 9, 1),
            date(2026, 9, 30),
            date(2026, 10, 1),
        )
        self.assertEqual(amount, Decimal("0.00"))

    def test_create_prorated_charge_applies_prorated_amount(self):
        charge = create_prorated_charge(
            self.owner,
            self.workspace,
            occupancy=self.occupancy,
            charge_type="custom",
            period_amount=Decimal("30000.00"),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            description="Prorated rent",
        )
        self.assertEqual(charge.amount, Decimal("30000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.charges_amount, Decimal("30000.00"))

    def test_create_charge_is_workspace_scoped(self):
        other = User.objects.create_user("charge-other@example.com", "StrongPass123!")
        other_workspace = Workspace.objects.create(
            name="Other Charge Workspace",
            slug="other-charge-workspace",
            owner=other,
        )
        Membership.objects.create(workspace=other_workspace, user=other, role="owner")
        with self.assertRaisesMessage(ValidationError, "Occupancy not found"):
            create_charge(
                other,
                other_workspace,
                occupancy=self.occupancy,
                charge_type="maintenance",
                amount=Decimal("100.00"),
                charge_date=date(2026, 9, 10),
            )
