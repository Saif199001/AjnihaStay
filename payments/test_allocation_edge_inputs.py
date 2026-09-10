from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from payments.allocation_service import allocate_payment
from payments.models import Invoice, Payment
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class PaymentAllocationInputEdgeTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("alloc-input@example.com", "StrongPass123!")
        self.owner = owner
        self.workspace = Workspace.objects.create(name="Alloc Input", slug="alloc-input", owner=owner)
        Membership.objects.create(workspace=self.workspace, user=owner, role="owner")
        prop = Property.objects.create(owner=owner, workspace=self.workspace, name="Input Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
        unit = Unit.objects.create(property=prop, unit_type="room", unit_number="I-1", rent=Decimal("10000"))
        tenant = Tenant.objects.create(owner=owner, workspace=self.workspace, full_name="Input Tenant", phone="9999999999", permanent_address="Delhi")
        occ = Occupancy.objects.create(tenant=tenant, unit=unit, allotted_by=owner, rent=Decimal("10000"), check_in_date=date(2026, 9, 1), next_due_date=date(2026, 10, 1))
        self.invoice = Invoice.objects.create(occupancy=occ, billing_start=date(2026, 9, 1), billing_end=date(2026, 9, 30), rent_amount=Decimal("10000"), charges_amount=Decimal("0"), due_date=date(2026, 10, 1))
        self.payment = Payment.objects.create(workspace=self.workspace, invoice=None, amount=Decimal("10000"), payment_method="upi", payment_date=date(2026, 9, 6))

    def test_rejects_empty_and_malformed_requests(self):
        with self.assertRaisesMessage(ValidationError, "At least one invoice allocation is required"):
            allocate_payment(self.owner, self.workspace, self.payment, [])
        with self.assertRaisesMessage(ValidationError, "Invalid allocation entry"):
            allocate_payment(self.owner, self.workspace, self.payment, [None])

    def test_rejects_invalid_ids_and_amounts(self):
        for invoice_id in (None, 0, -1, "bad"):
            with self.subTest(invoice_id=invoice_id), self.assertRaises(ValidationError):
                allocate_payment(self.owner, self.workspace, self.payment, [{"invoice": invoice_id, "amount": "1000"}])
        for amount in ("0", "-1", "bad", "NaN", "Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                allocate_payment(self.owner, self.workspace, self.payment, [{"invoice": self.invoice.id, "amount": amount}])
