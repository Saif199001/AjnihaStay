from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.models import AdvanceCredit, AdvanceCreditApplication, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class AdvanceCreditApplicationModelInvariantTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("advance-credit-model@example.com")
        self.owner.set_unusable_password()
        self.owner.save(update_fields=["password"])
        self.workspace = Workspace.objects.create(
            name="Advance Credit Model Workspace",
            slug="advance-credit-model-workspace",
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
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )
        self.source_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("1000.00"),
            payment_method="bank",
            payment_date=date(2026, 9, 10),
        )
        self.credit = AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=self.source_payment,
            original_amount=Decimal("1000.00"),
        )

    def test_direct_orm_create_rejects_credit_over_available_amount(self):
        AdvanceCreditApplication.objects.create(
            credit=self.credit,
            invoice=self.invoice,
            amount=Decimal("700.00"),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit application exceeds available credit",
        ):
            AdvanceCreditApplication.objects.create(
                credit=self.credit,
                invoice=self.invoice,
                amount=Decimal("300.01"),
            )

        self.assertEqual(self.credit.applied_amount, Decimal("700.00"))
        self.assertEqual(self.credit.available_amount, Decimal("300.00"))

    def test_direct_orm_create_rejects_invoice_over_outstanding_amount(self):
        other_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("1000.00"),
            payment_method="cash",
            payment_date=date(2026, 9, 10),
        )
        PaymentAllocation.objects.create(
            payment=other_payment,
            invoice=self.invoice,
            amount=Decimal("900.00"),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Advance credit application exceeds invoice outstanding amount",
        ):
            AdvanceCreditApplication.objects.create(
                credit=self.credit,
                invoice=self.invoice,
                amount=Decimal("100.01"),
            )

        self.assertEqual(self.invoice.allocated_paid_amount, Decimal("900.00"))
        self.assertEqual(self.credit.applied_amount, Decimal("0"))

    def test_direct_orm_create_accepts_application_within_both_capacities(self):
        application = AdvanceCreditApplication.objects.create(
            credit=self.credit,
            invoice=self.invoice,
            amount=Decimal("1000.00"),
        )

        self.assertEqual(application.amount, Decimal("1000.00"))
        self.assertEqual(self.credit.available_amount, Decimal("0"))
        self.assertEqual(self.invoice.settled_paid_amount, Decimal("1000.00"))

    def test_direct_orm_create_preserves_tenant_workspace_boundary(self):
        other_owner = User.objects.create_user("other-advance-credit@example.com")
        other_owner.set_unusable_password()
        other_owner.save(update_fields=["password"])
        other_workspace = Workspace.objects.create(
            name="Other Advance Credit Workspace",
            slug="other-advance-credit-workspace",
            owner=other_owner,
        )
        Membership.objects.create(workspace=other_workspace, user=other_owner, role="owner")
        other_tenant = Tenant.objects.create(
            owner=other_owner,
            workspace=other_workspace,
            full_name="Other Tenant",
            phone="8888888888",
            permanent_address="Lucknow",
        )
        other_property = Property.objects.create(
            owner=other_owner,
            workspace=other_workspace,
            name="Other Property",
            property_type="pg",
            address="Other Address",
            city="Lucknow",
            state="Uttar Pradesh",
            pincode="226001",
        )
        other_unit = Unit.objects.create(
            property=other_property,
            unit_type="room",
            unit_number="B-1",
            rent=Decimal("10000.00"),
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            allotted_by=other_owner,
            rent=Decimal("10000.00"),
            check_in_date=date(2026, 1, 1),
            next_due_date=date(2026, 2, 1),
            billing_type="arrears",
            billing_cycle="monthly",
        )
        other_invoice = Invoice.objects.create(
            occupancy=other_occupancy,
            billing_start=date(2026, 1, 1),
            billing_end=date(2026, 1, 31),
            rent_amount=Decimal("1000.00"),
            charges_amount=Decimal("0.00"),
            due_date=date(2026, 2, 5),
        )

        with self.assertRaises(ValidationError):
            AdvanceCreditApplication.objects.create(
                credit=self.credit,
                invoice=other_invoice,
                amount=Decimal("100.00"),
            )
