from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.models import Invoice
from .models import Tenant, Occupancy, Charge
from unit.models import Unit, SubUnit


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


def create_occupancy(user, data):
    with transaction.atomic():
        try:
            tenant = Tenant.objects.get(id=data.get("tenant"), owner=user)
        except Tenant.DoesNotExist:
            raise ValidationError("Tenant not found")

        unit_id = data.get("unit")
        subunit_id = data.get("subunit")

        if not unit_id and not subunit_id:
            raise ValidationError("Unit or SubUnit required")

        if subunit_id:
            try:
                # Lock the parent Unit first so allocation of a whole Unit and
                # allocation of any SubUnit cannot race each other.
                unit = Unit.objects.select_for_update().select_related("property").get(
                    id=unit_id if unit_id else SubUnit.objects.filter(
                        id=subunit_id,
                        unit__property__owner=user,
                    ).values("unit_id").first()["unit_id"],
                    property__owner=user,
                )
            except (Unit.DoesNotExist, TypeError):
                raise ValidationError("Unit not found")

            try:
                subunit = SubUnit.objects.select_for_update().get(
                    id=subunit_id,
                    unit=unit,
                )
            except SubUnit.DoesNotExist:
                raise ValidationError("SubUnit not found")

            unit_id = unit.id
            subunit_id = subunit.id
        else:
            try:
                unit = Unit.objects.select_for_update().select_related("property").get(
                    id=unit_id,
                    property__owner=user,
                )
            except Unit.DoesNotExist:
                raise ValidationError("Unit not found")

        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            subunit_id=subunit_id,
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
        Invoice.objects.create(
            occupancy=occupancy,
            billing_start=data.get("check_in_date"),
            billing_end=data.get("next_due_date"),
            rent_amount=data.get("rent"),
            charges_amount=charges_amount,
            due_date=data.get("next_due_date"),
        )
        return occupancy


def get_tenants(user):
    return Tenant.objects.filter(owner=user)


def create_charge(user, data):
    with transaction.atomic():
        try:
            occupancy = Occupancy.objects.select_related("tenant").get(
                id=data.get("occupancy"),
                tenant__owner=user,
            )
        except Occupancy.DoesNotExist:
            raise ValidationError("Occupancy not found")

        charge = Charge.objects.create(
            occupancy=occupancy,
            charge_type=data.get("charge_type"),
            description=data.get("description"),
            amount=data.get("amount"),
            charge_date=data.get("charge_date"),
        )

        invoice = occupancy.invoices.filter(status="pending").last()
        if not invoice:
            raise ValidationError("No active invoice found")

        invoice.charges_amount += charge.amount
        invoice.total_amount = invoice.rent_amount + invoice.charges_amount
        invoice.save()
        return charge


def get_charges(occupancy_id, user):
    return Charge.objects.filter(
        occupancy_id=occupancy_id,
        occupancy__tenant__owner=user,
    )
