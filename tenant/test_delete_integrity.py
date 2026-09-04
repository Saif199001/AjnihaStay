from datetime import date
from decimal import Decimal

from django.db.models.deletion import ProtectedError
from django.test import TestCase

from accounts.models import User
from payments.models import Invoice, Payment
from properties.models import Property
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace

from .models import Charge, Occupancy, Tenant


class DeleteIntegrityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("delete-owner@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Delete Workspace",
            slug="delete-workspace",
            owner=self.owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Delete Property",
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
            rent=Decimal("10000.00"),
        )
        self.subunit = SubUnit.objects.create(
            unit=self.unit,
            subunit_number="A",
            rent=Decimal("5000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Delete Tenant",
            phone="9999999999",
            permanent_address="Delhi",
        )
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            subunit=self.subunit,
            allotted_by=self.owner,
            rent=Decimal("5000.00"),
            check_in_date=date(2026, 9, 1),
            next_due_date=date(2026, 10, 1),
        )
        self.invoice = self.occupancy.invoices.get()

    def test_tenant_delete_is_protected_when_occupancy_exists(self):
        with self.assertRaises(ProtectedError):
            self.tenant.delete()
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())
        self.assertTrue(Occupancy.objects.filter(pk=self.occupancy.pk).exists())

    def test_unit_delete_is_protected_when_occupancy_exists(self):
        with self.assertRaises(ProtectedError):
            self.unit.delete()
        self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())
        self.assertTrue(Occupancy.objects.filter(pk=self.occupancy.pk).exists())

    def test_subunit_delete_is_protected_when_occupancy_exists(self):
        with self.assertRaises(ProtectedError):
            self.subunit.delete()
        self.assertTrue(SubUnit.objects.filter(pk=self.subunit.pk).exists())
        self.assertTrue(Occupancy.objects.filter(pk=self.occupancy.pk).exists())

    def test_occupancy_delete_is_protected_by_financial_history(self):
        Charge.objects.create(
            occupancy=self.occupancy,
            charge_type="maintenance",
            amount=Decimal("250.00"),
            charge_date=date(2026, 9, 3),
        )
        with self.assertRaises(ProtectedError):
            self.occupancy.delete()
        self.assertTrue(Occupancy.objects.filter(pk=self.occupancy.pk).exists())
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertTrue(Charge.objects.filter(occupancy=self.occupancy).exists())

    def test_invoice_delete_is_protected_when_payment_exists(self):
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("1000.00"),
            payment_method="cash",
            payment_date=date(2026, 9, 4),
        )
        with self.assertRaises(ProtectedError):
            self.invoice.delete()
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertEqual(self.invoice.payments.count(), 1)

    def test_property_delete_is_protected_when_occupancy_history_exists(self):
        with self.assertRaises(ProtectedError):
            self.property.delete()
        self.assertTrue(Property.objects.filter(pk=self.property.pk).exists())
        self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())
        self.assertTrue(Occupancy.objects.filter(pk=self.occupancy.pk).exists())
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())

    def test_user_delete_is_protected_by_property_and_tenant_ownership(self):
        with self.assertRaises(ProtectedError):
            self.owner.delete()
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(Property.objects.filter(pk=self.property.pk).exists())
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())
