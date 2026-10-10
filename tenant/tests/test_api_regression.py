from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIClient

from accounts.services import create_user_account
from payments.models import Invoice, Payment, _allow_payment_creation
from payments.services import record_payment
from properties.services import create_property
from tenant.services import create_occupancy, create_tenant
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class TenantPaymentAPIRegressionTests(TestCase):
    """HTTP-level regression coverage for tenant and financial API contracts."""

    def setUp(self):
        self.owner = create_user_account(
            "api-regression-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "API Regression Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()
        owner_membership = self.owner.workspace_memberships.get()

        self.manager = create_user_account(
            "api-regression-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Manager Personal Workspace",
        )
        self.viewer = create_user_account(
            "api-regression-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Viewer Personal Workspace",
        )
        add_member(
            self.workspace,
            owner_membership,
            self.manager.email,
            Membership.ROLE_MANAGER,
        )
        add_member(
            self.workspace,
            owner_membership,
            self.viewer.email,
            Membership.ROLE_VIEWER,
        )

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "API Regression Property",
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
                "unit_number": "API-101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )
        self.client = APIClient()

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        active_workspace = workspace or self.workspace
        return {"HTTP_X_WORKSPACE_ID": str(active_workspace.pk)}

    def tenant_payload(self, **overrides):
        payload = {
            "full_name": "API Tenant",
            "phone": "9876543210",
            "permanent_address": "Test Address",
        }
        payload.update(overrides)
        return payload

    def create_tenant_record(self, user=None, workspace=None):
        return create_tenant(
            user or self.owner,
            workspace or self.workspace,
            self.tenant_payload(),
            MultiValueDict(),
        )

    def create_occupancy_record(self):
        tenant = self.create_tenant_record()
        return create_occupancy(
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

    def create_payment_record(self, occupancy=None):
        occupancy = occupancy or self.create_occupancy_record()
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

    def test_tenant_create_api_manager_allowed_and_viewer_denied(self):
        headers = self.authenticate(self.manager)
        response = self.client.post(
            "/api/tenants/create/",
            self.tenant_payload(),
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["workspace"], self.workspace.pk)

        headers = self.authenticate(self.viewer)
        response = self.client.post(
            "/api/tenants/create/",
            self.tenant_payload(full_name="Viewer Attempt"),
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_list_api_is_workspace_scoped(self):
        own_tenant = self.create_tenant_record()
        other_owner = create_user_account(
            "api-regression-other@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Other API Workspace",
        )
        other_workspace = other_owner.owned_workspaces.get()
        other_tenant = self.create_tenant_record(other_owner, other_workspace)

        response = self.client.get("/api/tenants/", **self.authenticate(self.owner))
        self.assertEqual(response.status_code, 200, response.data)
        returned_ids = {item["id"] for item in response.data["data"]}
        self.assertIn(own_tenant.pk, returned_ids)
        self.assertNotIn(other_tenant.pk, returned_ids)

    def test_occupancy_create_api_enforces_rent_contract(self):
        tenant = self.create_tenant_record()
        payload = {
            "tenant": tenant.pk,
            "unit": self.unit.pk,
            "rent": "0.00",
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": "2026-10-01",
            "next_due_date": "2026-11-01",
            "security_deposit": "0.00",
            "deposit_paid": False,
        }
        headers = self.authenticate(self.manager)
        response = self.client.post(
            "/api/occupancy/create/", payload, format="json", **headers
        )
        self.assertEqual(response.status_code, 400)

        payload["rent"] = "10000.00"
        response = self.client.post(
            "/api/occupancy/create/", payload, format="json", **headers
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["tenant"], tenant.pk)
        self.assertEqual(
            Invoice.objects.filter(occupancy_id=response.data["data"]["id"]).count(),
            1,
        )

    def test_charge_create_and_list_api_contract(self):
        occupancy = self.create_occupancy_record()
        headers = self.authenticate(self.manager)
        response = self.client.post(
            "/api/charges/create/",
            {
                "occupancy": occupancy.pk,
                "charge_type": "food",
                "amount": "250.00",
                "charge_date": "2026-10-05",
                "description": "Meal charge",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["occupancy"], occupancy.pk)

        response = self.client.get(
            "/api/charges/",
            {"occupancy": occupancy.pk},
            **self.authenticate(self.viewer),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["amount"], "250.00")

    def test_invoice_list_detail_and_disabled_create_api(self):
        occupancy = self.create_occupancy_record()
        invoice = occupancy.invoices.get()
        headers = self.authenticate(self.viewer)

        response = self.client.get("/api/invoices/", **headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(invoice.pk, {item["id"] for item in response.data["data"]})

        response = self.client.get(f"/api/invoices/{invoice.pk}/", **headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["id"], invoice.pk)

        response = self.client.post(
            "/api/invoices/create/",
            {"occupancy": occupancy.pk, "rent_amount": "1.00"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_payment_create_and_list_api_preserve_partial_payment_contract(self):
        occupancy = self.create_occupancy_record()
        invoice = occupancy.invoices.get()
        headers = self.authenticate(self.manager)
        response = self.client.post(
            "/api/payments/create/",
            {
                "invoice": invoice.pk,
                "amount": "1000.00",
                "payment_method": "cash",
                "payment_date": "2026-10-05",
                "notes": "Partial payment",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        payment_id = response.data["data"]["id"]
        self.assertEqual(response.data["data"]["workspace"], self.workspace.pk)

        response = self.client.get(
            "/api/payments/", {"invoice": invoice.pk}, **headers
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(payment_id, {item["id"] for item in response.data["data"]})

        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1000.00"))

    def test_payment_create_api_denies_viewer_and_rejects_nonpositive_amount(self):
        occupancy = self.create_occupancy_record()
        invoice = occupancy.invoices.get()
        payload = {
            "invoice": invoice.pk,
            "amount": "0.00",
            "payment_method": "cash",
            "payment_date": "2026-10-05",
        }
        response = self.client.post(
            "/api/payments/create/",
            payload,
            format="json",
            **self.authenticate(self.manager),
        )
        self.assertEqual(response.status_code, 400)

        payload["amount"] = "100.00"
        response = self.client.post(
            "/api/payments/create/",
            payload,
            format="json",
            **self.authenticate(self.viewer),
        )
        self.assertEqual(response.status_code, 403)

    def test_billing_schedule_create_list_and_update_api(self):
        occupancy = self.create_occupancy_record()
        headers = self.authenticate(self.manager)
        response = self.client.post(
            "/api/billing-schedules/create/",
            {
                "occupancy": occupancy.pk,
                "frequency": "monthly",
                "amount": "10000.00",
                "next_run_date": "2026-11-01",
                "active": True,
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        schedule_id = response.data["data"]["id"]

        response = self.client.get("/api/billing-schedules/", **headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(schedule_id, {item["id"] for item in response.data["data"]})

        response = self.client.patch(
            f"/api/billing-schedules/{schedule_id}/update/",
            {"amount": "10500.00"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["amount"], "10500.00")

    def test_adjustment_and_refund_api_mutations_use_canonical_contracts(self):
        payment, invoice = self.create_payment_record()
        headers = self.authenticate(self.manager)

        response = self.client.post(
            "/api/financial-adjustments/create/",
            {
                "invoice": invoice.pk,
                "adjustment_type": "credit",
                "amount": "50.00",
                "reason": "API regression adjustment",
                "idempotency_key": "api-regression-adjustment-1",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["data"]["adjustment"]["invoice"], invoice.pk
        )

        response = self.client.post(
            f"/api/payments/{payment.pk}/refunds/",
            {
                "amount": "100.00",
                "reason": "API regression refund",
                "idempotency_key": "api-regression-refund-1",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        refund_id = response.data["data"]["id"]

        response = self.client.patch(
            f"/api/payment-refunds/{refund_id}/",
            {"status": "processing"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["status"], "processing")

    def test_financial_reports_validate_query_contract_and_are_readable(self):
        self.create_occupancy_record()
        headers = self.authenticate(self.viewer)

        response = self.client.get("/api/reports/receivables/", **headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("data", response.data)

        response = self.client.get(
            "/api/reports/aging/",
            {"as_of": "not-a-date"},
            **headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_payment_model_rows_are_not_exposed_across_workspace_api_context(self):
        payment, invoice = self.create_payment_record()
        other_owner = create_user_account(
            "api-regression-isolation@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Isolated API Workspace",
        )
        other_workspace = other_owner.owned_workspaces.get()

        response = self.client.get(
            "/api/payments/",
            {"invoice": invoice.pk},
            **self.authenticate(other_owner, other_workspace),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"], [])
        self.assertFalse(
            Payment.objects.filter(pk=payment.pk, workspace=other_workspace).exists()
        )


    def test_tenant_api_never_returns_kyc_fields_to_workspace_viewers(self):
        payload = self.tenant_payload(
            id_proof_type="aadhaar",
            id_number="TEST-KYC-1234",
        )
        response = self.client.post(
            "/api/tenants/create/",
            payload,
            format="json",
            **self.authenticate(self.manager),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("id_proof_type", response.data["data"])
        self.assertNotIn("id_number", response.data["data"])
        self.assertNotIn("id_document", response.data["data"])

        response = self.client.get("/api/tenants/", **self.authenticate(self.viewer))
        self.assertEqual(response.status_code, 200, response.data)
        for tenant_data in response.data["data"]:
            self.assertNotIn("id_proof_type", tenant_data)
            self.assertNotIn("id_number", tenant_data)
            self.assertNotIn("id_document", tenant_data)

    def test_payment_allocation_api_uses_canonical_boundary(self):
        occupancy = self.create_occupancy_record()
        invoice = occupancy.invoices.get()
        with _allow_payment_creation():
            payment = Payment.objects.create(
                workspace=self.workspace,
                invoice=None,
                amount=Decimal("1000.00"),
                payment_method="cash",
                payment_date=date(2026, 10, 5),
            )

        response = self.client.post(
            f"/api/payments/{payment.pk}/allocations/",
            {"allocations": [{"invoice": invoice.pk, "amount": "500.00"}]},
            format="json",
            **self.authenticate(self.manager),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"][0]["amount"], "500.00")
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("500.00"))

        denied = self.client.post(
            f"/api/payments/{payment.pk}/allocations/",
            {"allocations": [{"invoice": invoice.pk, "amount": "100.00"}]},
            format="json",
            **self.authenticate(self.viewer),
        )
        self.assertEqual(denied.status_code, 403)

    def test_advance_credit_api_create_apply_and_list_contract(self):
        tenant = self.create_tenant_record()
        response = self.client.post(
            "/api/payments/create/",
            {
                "tenant": tenant.pk,
                "amount": "1000.00",
                "payment_method": "cash",
                "payment_date": "2026-10-05",
                "notes": "Advance payment API regression",
            },
            format="json",
            **self.authenticate(self.manager),
        )
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.get(
            "/api/advance-credits/",
            **self.authenticate(self.viewer),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["data"]), 1)
        credit_id = response.data["data"][0]["id"]

        occupancy = create_occupancy(
            self.owner,
            self.workspace,
            self.occupancy_data(tenant),
        )
        invoice = occupancy.invoices.get()
        response = self.client.post(
            f"/api/advance-credits/{credit_id}/apply/",
            {"invoice": invoice.pk, "amount": "500.00"},
            format="json",
            **self.authenticate(self.manager),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["remaining_credit"], "500.00")

    def test_all_financial_report_endpoints_have_workspace_viewer_contract(self):
        occupancy = self.create_occupancy_record()
        invoice = occupancy.invoices.get()
        headers = self.authenticate(self.viewer)
        requests = [
            ("/api/reports/receivables/", {}),
            ("/api/reports/invoice/", {"invoice_id": invoice.pk}),
            ("/api/reports/invoice-status/", {}),
            ("/api/reports/collections/period/", {"start": "2026-10-01", "end": "2026-10-31"}),
            ("/api/reports/aging/", {"as_of": "2026-10-10"}),
            ("/api/reports/advance-credits/", {}),
            ("/api/reports/adjustments/", {}),
            ("/api/reports/late-fees/", {}),
            ("/api/reports/ledger/", {}),
            ("/api/reports/reconciliation/", {}),
        ]
        for path, params in requests:
            with self.subTest(path=path):
                response = self.client.get(path, params, **headers)
                self.assertEqual(response.status_code, 200, getattr(response, "data", None))
                self.assertIn("data", response.data)

    def test_viewer_cannot_finalize_final_settlement(self):
        occupancy = self.create_occupancy_record()
        response = self.client.post(
            f"/api/final-settlement/{occupancy.pk}/settle/",
            {},
            format="json",
            **self.authenticate(self.viewer),
        )
        self.assertEqual(response.status_code, 403)
