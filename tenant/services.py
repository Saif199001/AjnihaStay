from .models import Tenant, Occupancy, Charge
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal
from payments.models import Invoice

def create_tenant(user, data, files):

    if not data.get("full_name"):
        raise ValidationError("Full name required")

    if not data.get("phone"):
        raise ValidationError("Phone number required")

    return Tenant.objects.create(
        owner=user,
        full_name=data.get("full_name"),
        phone=data.get("phone"),
        email=data.get("email"),
        profile_photo=files.get("profile_photo"),
        nationality=data.get("nationality") or "Indian",
        id_proof_type=data.get("id_proof_type"),
        id_number=data.get("id_number"),
        id_document=files.get("id_document"),
        permanent_address=data.get("permanent_address"),
        district=data.get("district"),
        state=data.get("state"),
        pin_code=data.get("pin_code"),
        emergency_contact=data.get("emergency_contact"),
    )


# 🔥 CREATE TENANT (ALL FIELDS SUPPORT)
def create_occupancy(user, data):

    with transaction.atomic():   # 🔥 TRANSACTION START

        # 🔐 Ownership check (add if missing)
        try:
            tenant = Tenant.objects.get(id=data.get("tenant"))
        except Tenant.DoesNotExist:
            raise ValidationError("Tenant not found")

        if tenant.owner != user:
            raise ValidationError("Unauthorized")

        if not data.get("unit") and not data.get("subunit"):
            raise ValidationError("Unit or SubUnit required")

        # ✅ CREATE OCCUPANCY
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit_id=data.get("unit"),
            subunit_id=data.get("subunit"),
            allotted_by=user,
            rent=data.get("rent"),
            billing_type=data.get("billing_type"),
            billing_cycle=data.get("billing_cycle"),
            check_in_date=data.get("check_in_date"),
            next_due_date=data.get("next_due_date"),
            security_deposit=data.get("security_deposit") or 0,
            deposit_paid=data.get("deposit_paid") or False,
        )

        charges_amount = Decimal(data.get("charges_amount") or 0)

        # 🔥 AUTO CREATE INVOICE
        invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=data.get("check_in_date"),
            billing_end=data.get("next_due_date"),
            rent_amount=data.get("rent"),
            charges_amount=charges_amount,
            due_date=data.get("next_due_date"),
        )

        return occupancy


# 🔥 GET TENANTS
def get_tenants(user):
    return Tenant.objects.filter(owner=user)


# 🔥 CREATE CHARGE
def create_charge(user, data):

    with transaction.atomic():

        occupancy = Occupancy.objects.get(id=data.get("occupancy"))

        if occupancy.tenant.owner != user:
            raise ValidationError("Unauthorized")

        charge = Charge.objects.create(
            occupancy=occupancy,
            charge_type=data.get("charge_type"),
            description=data.get("description"),
            amount=data.get("amount"),
            charge_date=data.get("charge_date"),
        )

        # 🔥 GET LATEST INVOICE
        invoice = occupancy.invoices.filter(status="pending").last()

        if not invoice:
            raise ValidationError("No active invoice found")

        # 🔥 UPDATE INVOICE
        invoice.charges_amount += charge.amount
        invoice.total_amount = invoice.rent_amount + invoice.charges_amount
        invoice.save()

        return charge


# 🔥 GET CHARGES (BY OCCUPANCY)
def get_charges(occupancy_id, user):
    return Charge.objects.filter(occupancy_id=occupancy_id, occupancy__tenant__owner=user
    )