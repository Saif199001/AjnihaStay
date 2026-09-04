from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.services import calculate_final_settlement, create_payment
from properties.models import Property
from unit.models import Unit
from workspaces.models import Membership, Workspace

from .models import Charge, Occupancy, Tenant
from .services import create_charge, create_occupancy


class Phase2FinalRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("phase2-owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("phase2-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="Phase 2 Workspace",
            slug="phase2-workspace",
            owner=self.owner,
        )
        self.other_workspace = Workspace.objects.create(
            name="Phase 2 Other Workspace",
            slug="phase2-other-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Phase 2 Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="201",
            rent=Decimal("10000.00"),
        )
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Phase 2 Tenant",
            phone="9999999998",
            permanent_address="Delhi",
        )

    def test_final_phase2_domain_flow_preserves_consistency_and_isolation(self):
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            {
                "tenant": self.tenant,
                "unit": self.unit,
                "rent": Decimal("10000.00"),
                "billing_type": "advance",
                "billing_cycle": "monthly",
                "check_in_date": date(2026, 9, 1),
                "next_due_date": date(2026, 10, 1),
                "security_deposit": Decimal("2000.00"),
                "deposit_paid": True,
            },
        )
        invoice = occupancy.invoices.get()

        charge = create_charge(
            self.owner,
            self.workspace,
            {
                "occupancy": occupancy,
                "charge_type": "maintenance",
                "amount": Decimal("500.00"),
                "charge_date": date(2026, 9, 3),
            },
        )
        invoice.refresh_from_db()
        self.assertEqual(charge.amount, Decimal("500.00"))
        self.assertEqual(invoice.charges_amount, Decimal("500.00"))
        self.assertEqual(invoice.total_amount, Decimal("10500.00"))

        create_payment(
            self.owner,
            self.workspace,
            {
                "invoice": invoice.id,
                "amount": Decimal("6000.00"),
                "payment_method": "upi",
                "payment_date": date(2026, 9, 4),
            },
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("6000.00"))
        self.assertEqual(invoice.status, "partial")
        self.assertEqual(invoice.due_amount, Decimal("4500.00"))

        settlement = calculate_final_settlement(occupancy.id, self.workspace)
        self.assertEqual(settlement["total_paid"], Decimal("6000.00"))
        self.assertEqual(settlement["total_due"], Decimal("4500.00"))
        self.assertEqual(settlement["security_deposit"], Decimal("2000.00"))
        self.assertEqual(settlement["final_balance"], Decimal("2500.00"))

        with self.assertRaises(ValidationError):
            create_payment(
                self.other_owner,
                self.other_workspace,
                {
                    "invoice": invoice.id,
                    "amount": Decimal("100.00"),
                    "payment_method": "upi",
                    "payment_date": date(2026, 9, 4),
                },
            )

        self.assertEqual(Occupancy.objects.filter(workspace=self.workspace).count(), 1)
        self.assertEqual(Occupancy.objects.filter(workspace=self.other_workspace).count(), 0)
