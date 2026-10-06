from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from payments.models import AdvanceCredit, Invoice, Payment, PaymentAllocation, _allow_payment_creation
from payments.ledger_models import FinancialLedgerEntry
from payments.invoice_generation_service import generate_invoice_for_occupancy

from accounts.services import create_user_account
from properties.services import create_property
from tenant.models import (
    Charge,
    Occupancy,
    Tenant,
    _allow_occupancy_mutation,
)
from tenant.services import create_charge, create_occupancy, create_tenant, get_charges, get_tenants
from payments.services import record_payment
from payments.advance_credit_service import apply_advance_credit, create_advance_credit
from unit.models import SubUnit, _allow_unit_mutation
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member, archive_workspace


class TenantServiceAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = create_user_account(
            "tenant-service-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Service Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.manager = create_user_account(
            "tenant-service-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Manager Workspace",
        )
        self.viewer = create_user_account(
            "tenant-service-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Viewer Workspace",
        )
        owner_membership = self.owner.workspace_memberships.get()
        add_member(self.workspace, owner_membership, self.manager.email, Membership.ROLE_MANAGER)
        add_member(self.workspace, owner_membership, self.viewer.email, Membership.ROLE_VIEWER)

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Tenant Service Property",
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

    def tenant_data(self):
        return {
            "full_name": "Test Tenant",
            "phone": "9876543210",
            "permanent_address": "Test Address",
        }

    def occupancy_data(self, tenant):
        return {
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
        }

    def test_viewer_cannot_create_tenant_through_service(self):
        with self.assertRaises(PermissionDenied):
            create_tenant(self.viewer, self.workspace, self.tenant_data(), MultiValueDict())

    def test_viewer_cannot_create_occupancy_through_service(self):
        tenant = create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        with self.assertRaises(PermissionDenied):
            create_occupancy(self.viewer, self.workspace, self.occupancy_data(tenant))

    def test_manager_can_create_tenant_through_service(self):
        tenant = create_tenant(
            self.manager,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        self.assertEqual(tenant.owner_id, self.manager.pk)
        self.assertEqual(tenant.workspace_id, self.workspace.pk)

    def test_manager_can_create_occupancy_through_service(self):
        tenant = create_tenant(
            self.manager,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

        occupancy = create_occupancy(
            self.manager,
            self.workspace,
            self.occupancy_data(tenant),
        )

        self.assertEqual(occupancy.tenant_id, tenant.pk)
        self.assertEqual(occupancy.unit_id, self.unit.pk)
        self.assertEqual(occupancy.allotted_by_id, self.manager.pk)

    def test_archived_workspace_rejects_tenant_mutation_and_reads(self):
        tenant = create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )
        archive_workspace(self.workspace, self.owner.workspace_memberships.get())

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_tenant(self.owner, self.workspace, self.tenant_data(), MultiValueDict())

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(tenant))

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            create_charge(
                self.owner,
                self.workspace,
                {
                    "occupancy": occupancy.pk,
                    "charge_type": "food",
                    "amount": Decimal("100"),
                    "charge_date": date(2026, 10, 1),
                },
            )

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            get_tenants(self.workspace)

        with self.assertRaisesMessage(ValidationError, "Workspace is archived"):
            get_charges(occupancy.pk, self.workspace)


class TenantMutationBoundaryTests(TenantServiceAuthorizationTests):
    def create_tenant_record(self):
        return create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

    def create_occupancy_record(self, tenant):
        return create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )

    def create_charge_record(self, occupancy):
        return create_charge(
            self.owner,
            self.workspace,
            {
                "occupancy": occupancy.pk,
                "charge_type": "food",
                "amount": Decimal("100"),
                "charge_date": date(2026, 10, 1),
            },
        )

    def test_tenant_direct_save_is_blocked(self):
        tenant = self.create_tenant_record()
        tenant.phone = "9999999999"

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            tenant.save()

    def test_tenant_queryset_update_is_blocked(self):
        tenant = self.create_tenant_record()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            Tenant.objects.filter(pk=tenant.pk).update(phone="9999999999")

    def test_tenant_bulk_update_is_blocked(self):
        tenant = self.create_tenant_record()
        tenant.phone = "9999999999"

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            Tenant.objects.bulk_update([tenant], ["phone"])

    def test_tenant_bulk_create_is_blocked(self):
        tenant = Tenant(
            owner=self.owner,
            workspace=self.workspace,
            full_name="Bulk Tenant",
            phone="9999999998",
            permanent_address="Test Address",
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            Tenant.objects.bulk_create([tenant])

    def test_tenant_delete_is_blocked(self):
        tenant = self.create_tenant_record()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            tenant.delete()

    def test_tenant_queryset_delete_is_blocked(self):
        tenant = self.create_tenant_record()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant state must be changed through the canonical tenant service.",
        ):
            Tenant.objects.filter(pk=tenant.pk).delete()

    def test_tenant_workspace_reassignment_is_blocked_on_save(self):
        tenant = self.create_tenant_record()
        target_owner = create_user_account(
            "tenant-target-workspace@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Target Workspace",
        )
        target_workspace = target_owner.owned_workspaces.get()
        tenant.workspace = target_workspace

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant workspace cannot be reassigned.",
        ):
            tenant.save()

        tenant.refresh_from_db()
        self.assertEqual(tenant.workspace_id, self.workspace.pk)

    def test_tenant_workspace_reassignment_is_blocked_on_queryset_update(self):
        tenant = self.create_tenant_record()
        target_owner = create_user_account(
            "tenant-target-update@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Target Update Workspace",
        )
        target_workspace = target_owner.owned_workspaces.get()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant workspace cannot be reassigned.",
        ):
            Tenant.objects.filter(pk=tenant.pk).update(workspace=target_workspace)

        tenant.refresh_from_db()
        self.assertEqual(tenant.workspace_id, self.workspace.pk)

    def test_tenant_workspace_reassignment_is_blocked_on_bulk_update(self):
        tenant = self.create_tenant_record()
        target_owner = create_user_account(
            "tenant-target-bulk@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Tenant Target Bulk Workspace",
        )
        target_workspace = target_owner.owned_workspaces.get()
        tenant.workspace = target_workspace

        with self.assertRaisesMessage(
            PermissionDenied,
            "Tenant workspace cannot be reassigned.",
        ):
            Tenant.objects.bulk_update([tenant], ["workspace"])

        tenant.refresh_from_db()
        self.assertEqual(tenant.workspace_id, self.workspace.pk)

    def test_occupancy_direct_save_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        occupancy.rent = Decimal("9000")

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            occupancy.save()

    def test_occupancy_queryset_update_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            Occupancy.objects.filter(pk=occupancy.pk).update(rent=Decimal("9000"))

    def test_occupancy_bulk_update_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        occupancy.rent = Decimal("9000")

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            Occupancy.objects.bulk_update([occupancy], ["rent"])

    def test_occupancy_bulk_create_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = Occupancy(
            tenant=tenant,
            unit=self.unit,
            rent=Decimal("10000"),
            billing_type="advance",
            billing_cycle="monthly",
            check_in_date=date(2027, 1, 1),
            next_due_date=date(2027, 2, 1),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            Occupancy.objects.bulk_create([occupancy])

    def test_occupancy_delete_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            occupancy.delete()

    def test_occupancy_queryset_delete_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Occupancy state must be changed through the canonical occupancy service.",
        ):
            Occupancy.objects.filter(pk=occupancy.pk).delete()

    def test_charge_direct_save_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = self.create_charge_record(occupancy)
        charge.amount = Decimal("200")

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            charge.save()

    def test_charge_queryset_update_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = self.create_charge_record(occupancy)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            Charge.objects.filter(pk=charge.pk).update(amount=Decimal("200"))

    def test_charge_bulk_update_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = self.create_charge_record(occupancy)
        charge.amount = Decimal("200")

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            Charge.objects.bulk_update([charge], ["amount"])

    def test_charge_bulk_create_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = Charge(
            occupancy=occupancy,
            charge_type="food",
            amount=Decimal("100"),
            charge_date=date(2026, 10, 1),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            Charge.objects.bulk_create([charge])

    def test_charge_delete_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = self.create_charge_record(occupancy)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            charge.delete()

    def test_charge_queryset_delete_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        charge = self.create_charge_record(occupancy)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Charge state must be changed through the canonical charge service.",
        ):
            Charge.objects.filter(pk=charge.pk).delete()


class PaymentMutationBoundaryTests(TenantServiceAuthorizationTests):
    def create_payment_record(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        invoice = occupancy.invoices.get()
        payment = Payment(
            workspace=self.workspace,
            invoice=invoice,
            amount=Decimal("1000"),
            payment_method="cash",
            payment_date=date(2026, 10, 5),
        )
        return payment, invoice

    def create_tenant_record(self):
        return create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

    def create_occupancy_record(self, tenant):
        return create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )

    def test_payment_direct_create_is_blocked(self):
        payment, invoice = self.create_payment_record()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment creation must be performed through the canonical payment service.",
        ):
            Payment.objects.create(
                workspace=self.workspace,
                invoice=invoice,
                amount=Decimal("1000"),
                payment_method="cash",
                payment_date=date(2026, 10, 5),
            )

    def test_payment_direct_save_is_blocked(self):
        payment, _ = self.create_payment_record()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment creation must be performed through the canonical payment service.",
        ):
            payment.save(force_insert=True)

    def test_payment_bulk_create_is_blocked(self):
        _, invoice = self.create_payment_record()
        payment = Payment(
            workspace=self.workspace,
            invoice=invoice,
            amount=Decimal("1000"),
            payment_method="cash",
            payment_date=date(2026, 10, 5),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment creation must be performed through the canonical payment service.",
        ):
            Payment.objects.bulk_create([payment])

    def test_canonical_payment_service_can_create_payment(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        invoice = occupancy.invoices.get()

        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": invoice.pk,
                "amount": Decimal("1000"),
                "payment_method": "cash",
                "payment_date": date(2026, 10, 5),
            },
        )

        self.assertEqual(payment.workspace_id, self.workspace.pk)
        self.assertEqual(payment.invoice_id, invoice.pk)
        self.assertEqual(payment.amount, Decimal("1000.00"))


    def create_allocation_record(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        invoice = occupancy.invoices.get()
        payment = record_payment(
            self.owner,
            self.workspace,
            {
                "invoice": invoice.pk,
                "amount": Decimal("1000"),
                "payment_method": "cash",
                "payment_date": date(2026, 10, 5),
            },
        )
        return payment, invoice

    def test_payment_allocation_direct_create_is_blocked(self):
        payment, invoice = self.create_allocation_record()
        allocation = PaymentAllocation(
            payment=payment,
            invoice=invoice,
            amount=Decimal("1"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment allocation creation must be performed through the canonical payment service.",
        ):
            allocation.save()

    def test_payment_allocation_bulk_create_is_blocked(self):
        payment, invoice = self.create_allocation_record()
        allocation = PaymentAllocation(
            payment=payment,
            invoice=invoice,
            amount=Decimal("1"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Payment allocation creation must be performed through the canonical payment service.",
        ):
            PaymentAllocation.objects.bulk_create([allocation])

    def test_canonical_payment_service_creates_payment_allocation(self):
        payment, invoice = self.create_allocation_record()

        allocation = PaymentAllocation.objects.get(
            payment=payment,
            invoice=invoice,
        )
        self.assertEqual(allocation.amount, Decimal("1000.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1000.00"))

    def create_advance_credit_record(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        payment = Payment(
            workspace=self.workspace,
            amount=Decimal("500"),
            payment_method="cash",
            payment_date=date(2026, 10, 5),
        )
        with _allow_payment_creation():
            payment.save(force_insert=True)
        return payment, tenant, occupancy

    def test_advance_credit_direct_create_is_blocked(self):
        payment, tenant, occupancy = self.create_advance_credit_record()
        credit = AdvanceCredit(
            workspace=self.workspace,
            tenant=tenant,
            occupancy=occupancy,
            source_payment=payment,
            original_amount=Decimal("1"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit creation must be performed through the canonical advance credit service.",
        ):
            credit.save()

    def test_advance_credit_bulk_create_is_blocked(self):
        payment, tenant, occupancy = self.create_advance_credit_record()
        credit = AdvanceCredit(
            workspace=self.workspace,
            tenant=tenant,
            occupancy=occupancy,
            source_payment=payment,
            original_amount=Decimal("1"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit creation must be performed through the canonical advance credit service.",
        ):
            AdvanceCredit.objects.bulk_create([credit])

    def test_canonical_advance_credit_service_can_create_credit(self):
        payment, tenant, occupancy = self.create_advance_credit_record()

        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": payment.pk,
                "tenant": tenant.pk,
                "occupancy": occupancy.pk,
                "amount": Decimal("500"),
            },
        )

        self.assertEqual(credit.workspace_id, self.workspace.pk)
        self.assertEqual(credit.tenant_id, tenant.pk)
        self.assertEqual(credit.occupancy_id, occupancy.pk)
        self.assertEqual(credit.source_payment_id, payment.pk)
        self.assertEqual(credit.original_amount, Decimal("500.00"))


    def create_advance_credit_application_record(self):
        payment, tenant, occupancy = self.create_advance_credit_record()
        credit = create_advance_credit(
            self.owner,
            self.workspace,
            {
                "source_payment": payment.pk,
                "tenant": tenant.pk,
                "occupancy": occupancy.pk,
                "amount": Decimal("500"),
            },
        )
        invoice = occupancy.invoices.get()
        return credit, invoice

    def test_advance_credit_application_direct_create_is_blocked(self):
        credit, invoice = self.create_advance_credit_application_record()
        application = AdvanceCreditApplication(
            credit=credit,
            invoice=invoice,
            amount=Decimal("100"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit application creation must be performed through the canonical advance credit service.",
        ):
            application.save()

    def test_advance_credit_application_bulk_create_is_blocked(self):
        credit, invoice = self.create_advance_credit_application_record()
        application = AdvanceCreditApplication(
            credit=credit,
            invoice=invoice,
            amount=Decimal("100"),
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit application creation must be performed through the canonical advance credit service.",
        ):
            AdvanceCreditApplication.objects.bulk_create([application])

    def test_canonical_advance_credit_application_service_can_create_application(self):
        credit, invoice = self.create_advance_credit_application_record()

        application, available_credit, updated_invoice = apply_advance_credit(
            self.owner,
            self.workspace,
            {
                "credit": credit.pk,
                "invoice": invoice.pk,
                "amount": Decimal("100"),
            },
        )

        self.assertEqual(application.credit_id, credit.pk)
        self.assertEqual(application.invoice_id, invoice.pk)
        self.assertEqual(application.amount, Decimal("100.00"))
        self.assertEqual(available_credit, Decimal("400.00"))
        self.assertEqual(updated_invoice.pk, invoice.pk)

    def test_advance_credit_application_delete_is_blocked(self):
        credit, invoice = self.create_advance_credit_application_record()
        application, _, _ = apply_advance_credit(
            self.owner,
            self.workspace,
            {
                "credit": credit.pk,
                "invoice": invoice.pk,
                "amount": Decimal("100"),
            },
        )

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit applications cannot be deleted.",
        ):
            application.delete()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Advance credit applications cannot be deleted.",
        ):
            AdvanceCreditApplication.objects.filter(pk=application.pk).delete()


class OccupancyStructureInvariantTests(TenantServiceAuthorizationTests):
    def create_tenant_record(self):
        return create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

    def _create_shop_with_legacy_subunit(self):
        shop_property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Legacy Shop Property",
                "property_type": "shop",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )
        shop_unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": shop_property,
                "unit_number": "S-101",
                "unit_type": "shop",
                "rent": Decimal("15000"),
                "capacity": 1,
                "description": "",
            },
        )
        with _allow_unit_mutation():
            subunit = SubUnit.objects.create(
                unit=shop_unit,
                subunit_number="S-101-A",
                rent=Decimal("15000"),
            )
        return shop_unit, subunit

    def test_subunit_occupancy_is_rejected_for_non_subunit_property(self):
        shop_unit, subunit = self._create_shop_with_legacy_subunit()
        tenant = self.create_tenant_record()
        data = self.occupancy_data(tenant)
        data.update(
            {
                "unit": shop_unit.pk,
                "subunit": subunit.pk,
                "check_in_date": date(2026, 12, 1),
                "next_due_date": date(2027, 1, 1),
            }
        )

        with self.assertRaisesMessage(
            ValidationError,
            "SubUnit occupancy is not allowed for this property type",
        ):
            create_occupancy(self.owner, self.workspace, data)

    def test_occupancy_model_rejects_subunit_for_non_subunit_property(self):
        shop_unit, subunit = self._create_shop_with_legacy_subunit()
        tenant = self.create_tenant_record()
        occupancy = Occupancy(
            tenant=tenant,
            unit=shop_unit,
            subunit=subunit,
            allotted_by=self.owner,
            rent=Decimal("15000"),
            billing_type="advance",
            billing_cycle="monthly",
            check_in_date=date(2027, 2, 1),
            next_due_date=date(2027, 3, 1),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "SubUnit occupancy is not allowed for this property type",
        ):
            with _allow_occupancy_mutation():
                occupancy.save()


class InvoiceFinancialBoundaryTests(TenantServiceAuthorizationTests):
    def create_tenant_record(self):
        return create_tenant(
            self.owner,
            self.workspace,
            self.tenant_data(),
            MultiValueDict(),
        )

    def create_occupancy_record(self, tenant):
        return create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )

    def test_occupancy_ignores_caller_supplied_charges_amount(self):
        tenant = self.create_tenant_record()
        data = self.occupancy_data(tenant)
        data["charges_amount"] = Decimal("99999")

        occupancy = create_occupancy(self.owner, self.workspace, data)
        invoice = occupancy.invoices.get()

        self.assertEqual(invoice.charges_amount, Decimal("0.00"))
        self.assertEqual(invoice.total_amount, Decimal("10000.00"))

    def test_direct_invoice_creation_is_blocked(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)

        with self.assertRaisesMessage(
            PermissionDenied,
            "Invoice creation must be performed through the canonical invoice service.",
        ):
            Invoice.objects.create(
                occupancy=occupancy,
                billing_start=date(2026, 11, 1),
                billing_end=date(2026, 12, 1),
                rent_amount=Decimal("10000"),
                charges_amount=Decimal("500"),
                due_date=date(2026, 12, 1),
            )


    def test_occupancy_creation_posts_initial_invoice_ledger_event(self):
        tenant = self.create_tenant_record()

        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )
        invoice = occupancy.invoices.get()

        entry = FinancialLedgerEntry.objects.get(
            workspace=self.workspace,
            event_key=f"invoice:{invoice.pk}:created",
        )
        self.assertEqual(entry.event_type, "invoice_created")
        self.assertEqual(entry.invoice_id, invoice.pk)
        self.assertEqual(entry.occupancy_id, occupancy.pk)
        self.assertEqual(entry.amount, invoice.total_amount)
        self.assertEqual(entry.amount, Decimal("10000.00"))

    def test_occupancy_initial_invoice_ledger_event_is_idempotent(self):
        tenant = self.create_tenant_record()
        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )
        invoice = occupancy.invoices.get()

        self.assertEqual(
            FinancialLedgerEntry.objects.filter(
                workspace=self.workspace,
                event_key=f"invoice:{invoice.pk}:created",
            ).count(),
            1,
        )

    def test_occupancy_invoice_and_ledger_roll_back_together(self):
        tenant = self.create_tenant_record()
        data = self.occupancy_data(tenant)

        with patch(
            "payments.invoice_generation_service.post_ledger_event",
            side_effect=ValidationError("forced ledger failure"),
        ):
            with self.assertRaisesMessage(
                ValidationError,
                "forced ledger failure",
            ):
                create_occupancy(self.owner, self.workspace, data)

        self.assertFalse(
            Occupancy.objects.filter(
                tenant=tenant,
                unit=self.unit,
            ).exists()
        )
        self.assertFalse(
            Invoice.objects.filter(
                occupancy__tenant=tenant,
            ).exists()
        )
        self.assertFalse(
            FinancialLedgerEntry.objects.filter(
                workspace=self.workspace,
                occupancy__tenant=tenant,
            ).exists()
        )

    def test_canonical_invoice_generation_derives_charges_from_charge_records(self):
        tenant = self.create_tenant_record()
        occupancy = self.create_occupancy_record(tenant)
        from tenant.services import create_charge

        create_charge(
            self.owner,
            self.workspace,
            {
                "occupancy": occupancy.pk,
                "charge_type": "food",
                "amount": Decimal("250"),
                "charge_date": date(2026, 11, 5),
            },
        )

        invoice, created = generate_invoice_for_occupancy(
            self.owner,
            self.workspace,
            occupancy,
            date(2026, 11, 1),
            date(2026, 12, 1),
            date(2026, 12, 1),
        )

        self.assertTrue(created)
        self.assertEqual(invoice.charges_amount, Decimal("250.00"))
        self.assertEqual(invoice.total_amount, Decimal("10250.00"))
