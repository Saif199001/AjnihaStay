from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from payments.final_settlement import FinalSettlement, finalize_final_settlement
from payments.ledger_models import FinancialLedgerEntry
from payments.services import record_payment
from properties.services import create_property
from tenant.models import _allow_occupancy_mutation
from tenant.services import create_occupancy, create_tenant
from unit.services import create_unit


class FinalSettlementMutationBoundaryTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "final-settlement-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Final Settlement Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Final Settlement Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )
        self.unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )

    def create_settled_occupancy(self):
        tenant = create_tenant(
            self.owner,
            self.workspace,
            {
                "full_name": "Final Settlement Tenant",
                "phone": "9876543210",
                "permanent_address": "Test Address",
            },
            MultiValueDict(),
        )
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            {
                "tenant": tenant.pk,
                "unit": self.unit.pk,
                "rent": Decimal("10000"),
                "billing_type": "advance",
                "billing_cycle": "monthly",
                "check_in_date": date(2026, 10, 1),
                "check_out_date": None,
                "next_due_date": date(2026, 11, 1),
                "security_deposit": Decimal("10000"),
                "deposit_paid": False,
            },
        )
        invoice = occupancy.invoices.get()
        record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": invoice.pk,
                "amount": Decimal("10000"),
                "payment_method": "cash",
                "payment_date": date(2026, 10, 8),
            },
        )
        occupancy.refresh_from_db()
        occupancy.check_out_date = date(2026, 10, 8)
        with _allow_occupancy_mutation():
            occupancy.save()
        return occupancy

    def settlement_data(self, occupancy):
        return {
            "workspace": self.workspace,
            "occupancy": occupancy,
            "total_rent": Decimal("10000.00"),
            "total_charges": Decimal("0.00"),
            "total_paid": Decimal("10000.00"),
            "total_due": Decimal("0.00"),
            "security_deposit": Decimal("10000.00"),
            "retained_deposit": Decimal("0.00"),
            "refundable_deposit": Decimal("10000.00"),
            "final_balance": Decimal("0.00"),
            "outcome": FinalSettlement.OUTCOME_FULL_REFUND,
            "settled_by": self.owner,
        }

    def test_direct_create_is_blocked(self):
        occupancy = self.create_settled_occupancy()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlement creation must be performed through the canonical final settlement service.",
        ):
            FinalSettlement.objects.create(**self.settlement_data(occupancy))

    def test_direct_save_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = FinalSettlement(**self.settlement_data(occupancy))

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlement creation must be performed through the canonical final settlement service.",
        ):
            settlement.save(force_insert=True)

    def test_bulk_create_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = FinalSettlement(**self.settlement_data(occupancy))

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlement creation must be performed through the canonical final settlement service.",
        ):
            FinalSettlement.objects.bulk_create([settlement])

    def test_canonical_service_can_create_settlement(self):
        occupancy = self.create_settled_occupancy()

        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )

        self.assertEqual(settlement.occupancy_id, occupancy.pk)
        self.assertEqual(settlement.total_due, Decimal("0.00"))
        self.assertEqual(settlement.refundable_deposit, Decimal("10000.00"))
        self.assertEqual(settlement.outcome, FinalSettlement.OUTCOME_FULL_REFUND)

        entry = FinancialLedgerEntry.objects.get(
            workspace=self.workspace,
            event_key=f"final-settlement:{settlement.pk}:finalized",
        )
        self.assertEqual(entry.event_type, "final_settlement_finalized")
        self.assertEqual(entry.occupancy_id, occupancy.pk)

    def test_existing_settlement_save_cannot_change_financial_facts(self):
        occupancy = self.create_settled_occupancy()
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )

        settlement.refundable_deposit = Decimal("5000.00")
        with self.assertRaisesMessage(
            ValidationError,
            "Final settlement facts cannot be changed after settlement",
        ):
            settlement.save()

    def test_queryset_update_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlement financial facts cannot be updated directly.",
        ):
            FinalSettlement.objects.filter(pk=settlement.pk).update(
                refundable_deposit=Decimal("5000.00"),
            )

    def test_bulk_update_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )
        settlement.refundable_deposit = Decimal("5000.00")

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlement financial facts cannot be updated directly.",
        ):
            FinalSettlement.objects.bulk_update([settlement], ["refundable_deposit"])

    def test_instance_delete_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlements cannot be deleted.",
        ):
            settlement.delete()

    def test_queryset_delete_is_blocked(self):
        occupancy = self.create_settled_occupancy()
        settlement = finalize_final_settlement(
            self.owner,
            self.workspace,
            occupancy.pk,
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Final settlements cannot be deleted.",
        ):
            FinalSettlement.objects.filter(pk=settlement.pk).delete()
