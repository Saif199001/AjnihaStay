from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace
from .models import Charge, Occupancy, Tenant
from .serializers import TenantSerializer
from .services import create_occupancy, create_charge, get_charges, get_tenants


class OccupancySecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Owner Workspace", slug="owner-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")
        self.property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="Test Property", property_type="pg", address="Test Address", city="Delhi", state="Delhi", pincode="110001")
        self.other_property = Property.objects.create(owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="pg", address="Other Address", city="Delhi", state="Delhi", pincode="110002")
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="101", rent=Decimal("10000.00"))
        self.other_unit = Unit.objects.create(property=self.other_property, unit_type="room", unit_number="201", rent=Decimal("9000.00"))
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Owner Tenant", phone="9999999999", permanent_address="Delhi")

    def occupancy_data(self, unit_id):
        return {"tenant": self.tenant.id, "unit": unit_id, "rent": Decimal("10000.00"), "billing_type": "advance", "billing_cycle": "monthly", "check_in_date": date(2026, 9, 1), "next_due_date": date(2026, 10, 1)}

    def test_cross_workspace_unit_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.other_unit.id))

    def test_cross_workspace_subunit_is_rejected(self):
        subunit = SubUnit.objects.create(unit=self.other_unit, subunit_number="A", rent=Decimal("5000.00"))
        data = self.occupancy_data(self.other_unit.id)
        data["subunit"] = subunit.id
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

    def test_overlapping_active_occupancy_is_rejected(self):
        Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, self.occupancy_data(self.unit.id))

    def test_occupancy_rejects_negative_rent(self):
        data = self.occupancy_data(self.unit.id)
        data["rent"] = Decimal("-1.00")
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

    def test_occupancy_rejects_negative_security_deposit(self):
        data = self.occupancy_data(self.unit.id)
        data["security_deposit"] = Decimal("-1.00")
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

    def test_occupancy_rejects_invalid_date_order(self):
        data = self.occupancy_data(self.unit.id)
        data["check_out_date"] = date(2026, 8, 31)
        with self.assertRaises(ValidationError):
            create_occupancy(self.owner, self.workspace, data)

    def test_tenant_serializer_cannot_assign_owner_or_workspace(self):
        serializer = TenantSerializer(data={"owner": self.other_owner.id, "workspace": self.other_workspace.id, "full_name": "Injected Tenant", "phone": "9999999998", "permanent_address": "Delhi"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("owner", serializer.validated_data)
        self.assertNotIn("workspace", serializer.validated_data)

    def test_get_tenants_is_workspace_scoped(self):
        Tenant.objects.create(owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant", phone="8888888888", permanent_address="Other Delhi")
        self.assertEqual(list(get_tenants(self.workspace).values_list("id", flat=True)), [self.tenant.id])

    def test_create_charge_rejects_cross_workspace_occupancy(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            create_charge(self.other_owner, self.other_workspace, {"occupancy": occupancy.id, "charge_type": "maintenance", "description": "Injected", "amount": Decimal("100.00"), "charge_date": date(2026, 9, 3)})

    def test_get_charges_is_workspace_scoped(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        self.assertEqual(get_charges(occupancy.id, self.other_workspace).count(), 0)

    def test_charge_rejects_non_positive_amount(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            Charge.objects.create(occupancy=occupancy, charge_type="maintenance", amount=Decimal("0.00"), charge_date=date(2026, 9, 3))

    def test_charge_rejects_date_before_checkin(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            Charge.objects.create(occupancy=occupancy, charge_type="maintenance", amount=Decimal("100.00"), charge_date=date(2026, 8, 31))

    def test_database_constraint_blocks_invalid_charge_row(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        with self.assertRaises(IntegrityError):
            Charge.objects.bulk_create([Charge(occupancy=occupancy, charge_type="maintenance", amount=Decimal("0.00"), charge_date=date(2026, 9, 3))])


class TenantWorkspaceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        password = "StrongPass123!"
        self.owner = User.objects.create_user("tenant-api-owner@example.com", password)
        self.other = User.objects.create_user("tenant-api-other@example.com", password)
        self.manager = User.objects.create_user("tenant-api-manager@example.com", password)
        self.staff = User.objects.create_user("tenant-api-staff@example.com", password)
        self.workspace = Workspace.objects.create(name="Tenant API", slug="tenant-api", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Tenant API", slug="other-tenant-api", owner=self.other)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager")
        Membership.objects.create(workspace=self.workspace, user=self.staff, role="staff")
        Membership.objects.create(workspace=self.other_workspace, user=self.other, role="owner")
        self.property = Property.objects.create(owner=self.owner, workspace=self.workspace, name="API Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        self.other_property = Property.objects.create(owner=self.other, workspace=self.other_workspace, name="Other API Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110002")
        self.unit = Unit.objects.create(property=self.property, unit_type="room", unit_number="201", rent=Decimal("12000.00"))
        self.other_unit = Unit.objects.create(property=self.other_property, unit_type="room", unit_number="301", rent=Decimal("9000.00"))
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="API Tenant", phone="7777777777", permanent_address="Delhi")

    def headers(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_WORKSPACE_ID": str((workspace or self.workspace).id)}

    def occupancy_payload(self, unit_id=None):
        return {
            "tenant": self.tenant.id,
            "unit": unit_id or self.unit.id,
            "rent": "12000.00",
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": "2026-09-01",
            "next_due_date": "2026-10-01",
        }

    def charge_payload(self, occupancy_id, amount="100.00"):
        return {
            "occupancy": occupancy_id,
            "charge_type": "maintenance",
            "description": "Test charge",
            "amount": amount,
            "charge_date": "2026-09-03",
        }

    def test_staff_cannot_create_tenant(self):
        response = self.client.post("/api/tenants/create/", {"full_name": "Blocked", "phone": "6666666666", "permanent_address": "Delhi"}, format="json", **self.headers(self.staff))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Tenant.objects.filter(full_name="Blocked").exists())

    def test_manager_can_create_tenant(self):
        response = self.client.post("/api/tenants/create/", {"full_name": "Manager Tenant", "phone": "6666666666", "permanent_address": "Delhi"}, format="json", **self.headers(self.manager))
        self.assertEqual(response.status_code, 200)
        created = Tenant.objects.get(full_name="Manager Tenant")
        self.assertEqual(created.workspace_id, self.workspace.id)
        self.assertEqual(created.owner_id, self.manager.id)

    def test_staff_cannot_create_occupancy(self):
        response = self.client.post("/api/occupancies/create/", self.occupancy_payload(), format="json", **self.headers(self.staff))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Occupancy.objects.count(), 0)

    def test_cross_workspace_occupancy_create_is_blocked(self):
        response = self.client.post("/api/occupancies/create/", self.occupancy_payload(self.other_unit.id), format="json", **self.headers(self.other, self.other_workspace))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Occupancy.objects.count(), 0)

    def test_invalid_occupancy_payload_returns_400_without_writes(self):
        payload = self.occupancy_payload()
        payload["check_out_date"] = "2026-08-31"
        response = self.client.post("/api/occupancies/create/", payload, format="json", **self.headers(self.manager))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Occupancy.objects.count(), 0)

    def test_charge_create_rolls_back_when_no_pending_invoice_exists(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("12000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        response = self.client.post("/api/charges/create/", self.charge_payload(occupancy.id), format="json", **self.headers(self.manager))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Charge.objects.filter(occupancy=occupancy).count(), 0)

    def test_charge_create_updates_active_invoice_atomically(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("12000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        from payments.models import Invoice
        invoice = Invoice.objects.create(occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1), rent_amount=Decimal("12000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1))
        response = self.client.post("/api/charges/create/", self.charge_payload(occupancy.id), format="json", **self.headers(self.manager))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Charge.objects.filter(occupancy=occupancy).count(), 1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.charges_amount, Decimal("100.00"))
        self.assertEqual(invoice.total_amount, Decimal("12100.00"))

    def test_charge_invalid_payload_returns_400_without_writes(self):
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=self.unit, allotted_by=self.owner, rent=Decimal("12000.00"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        from payments.models import Invoice
        Invoice.objects.create(occupancy=occupancy, billing_start=date(2026, 9, 1), billing_end=date(2026, 10, 1), rent_amount=Decimal("12000.00"), charges_amount=Decimal("0.00"), due_date=date(2026, 10, 1))
        response = self.client.post("/api/charges/create/", self.charge_payload(occupancy.id, "0.00"), format="json", **self.headers(self.manager))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Charge.objects.filter(occupancy=occupancy).count(), 0)
