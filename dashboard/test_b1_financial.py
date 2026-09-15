from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from dashboard.services import get_dashboard_data
from payments.models import AdvanceCredit, AdvanceCreditApplication, FinancialAdjustment, Invoice, Payment, PaymentAllocation
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace
from django.contrib.auth import get_user_model


User = get_user_model()


class DashboardCanonicalFinancialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="b1-dashboard@example.com", password="testpass123")
        self.workspace = Workspace.objects.create(name="B1 Workspace", slug="b1-dashboard-workspace", owner=self.user)
        Membership.objects.create(workspace=self.workspace, user=self.user, role=Membership.ROLE_OWNER)
        self.property = Property.objects.create(name="B1 Property", owner=self.user, workspace=self.workspace)
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="B1-101",
            rent=Decimal("10000"),
            capacity=1,
        )
        self.tenant = Tenant.objects.create(
            full_name="B1 Tenant",
            email="b1-tenant@example.com",
            phone="123",
            permanent_address="B1 Address",
            workspace=self.workspace,
            owner=self.user,
        )
        today = timezone.localdate()
        self.occupancy = Occupancy.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in_date=today - timedelta(days=30),
            next_due_date=today,
            rent=Decimal("10000"),
            security_deposit=Decimal("0"),
        )
        self.invoice = Invoice.objects.create(
            occupancy=self.occupancy,
            billing_start=today - timedelta(days=30),
            billing_end=today - timedelta(days=1),
            rent_amount=Decimal("10000"),
            charges_amount=Decimal("0"),
            due_date=today - timedelta(days=1),
        )

    def test_outstanding_uses_canonical_adjusted_receivable(self):
        FinancialAdjustment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("2000"),
            reason="Approved credit",
            created_by=self.user,
        )
        FinancialAdjustment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            adjustment_type=FinancialAdjustment.TYPE_DEBIT,
            amount=Decimal("500"),
            reason="Additional charge",
            created_by=self.user,
        )
        payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=self.invoice,
            amount=Decimal("3000"),
            payment_method="cash",
            payment_date=timezone.localdate(),
        )
        PaymentAllocation.objects.create(payment=payment, invoice=self.invoice, amount=Decimal("3000"))

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["financial"]["outstanding"], Decimal("5500"))
        self.assertEqual(data["financial"]["overdue"], Decimal("5500"))

    def test_overdue_ignores_legacy_invoice_paid_amount(self):
        self.invoice.paid_amount = Decimal("10000")
        self.invoice.status = "paid"
        # Direct update intentionally creates a stale compatibility value without invoking save().
        Invoice.objects.filter(id=self.invoice.id).update(paid_amount=Decimal("10000"), status="paid")

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["financial"]["outstanding"], Decimal("10000"))
        self.assertEqual(data["financial"]["overdue"], Decimal("10000"))

    def test_outstanding_includes_advance_credit_application(self):
        source_payment = Payment.objects.create(
            workspace=self.workspace,
            invoice=None,
            amount=Decimal("3000"),
            payment_method="cash",
            payment_date=timezone.localdate(),
        )
        credit = AdvanceCredit.objects.create(
            workspace=self.workspace,
            tenant=self.tenant,
            occupancy=self.occupancy,
            source_payment=source_payment,
            original_amount=Decimal("3000"),
        )
        AdvanceCreditApplication.objects.create(
            credit=credit,
            invoice=self.invoice,
            amount=Decimal("3000"),
        )

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["financial"]["outstanding"], Decimal("7000"))
        self.assertEqual(data["financial"]["overdue"], Decimal("7000"))

    def test_financial_position_is_workspace_isolated(self):
        other_user = User.objects.create_user(email="b1-other@example.com", password="testpass123")
        other_workspace = Workspace.objects.create(name="B1 Other", slug="b1-other-workspace", owner=other_user)
        Membership.objects.create(workspace=other_workspace, user=other_user, role=Membership.ROLE_OWNER)
        other_property = Property.objects.create(name="Other Property", owner=other_user, workspace=other_workspace)
        other_unit = Unit.objects.create(
            property=other_property,
            unit_type="room",
            unit_number="B1-201",
            rent=Decimal("9000"),
            capacity=1,
        )
        other_tenant = Tenant.objects.create(
            full_name="Other Tenant",
            email="b1-other-tenant@example.com",
            phone="123",
            permanent_address="Other Address",
            workspace=other_workspace,
            owner=other_user,
        )
        other_occupancy = Occupancy.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            check_in_date=timezone.localdate() - timedelta(days=30),
            next_due_date=timezone.localdate(),
            rent=Decimal("9000"),
            security_deposit=Decimal("0"),
        )
        other_invoice = Invoice.objects.create(
            occupancy=other_occupancy,
            billing_start=timezone.localdate() - timedelta(days=30),
            billing_end=timezone.localdate() - timedelta(days=1),
            rent_amount=Decimal("9000"),
            charges_amount=Decimal("0"),
            due_date=timezone.localdate() - timedelta(days=1),
        )
        FinancialAdjustment.objects.create(
            workspace=other_workspace,
            invoice=other_invoice,
            adjustment_type=FinancialAdjustment.TYPE_CREDIT,
            amount=Decimal("9000"),
            reason="Other workspace credit",
            created_by=other_user,
        )

        data = get_dashboard_data(self.workspace)

        self.assertEqual(data["financial"]["outstanding"], Decimal("10000"))
        self.assertEqual(data["financial"]["overdue"], Decimal("10000"))
