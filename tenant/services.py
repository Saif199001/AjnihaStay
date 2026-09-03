from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.models import Invoice
from unit.models import SubUnit, Unit
from .models import Charge, Occupancy, Tenant


def create_tenant(user, workspace, data, files):
    if not data.get("full_name"):
        raise ValidationError("Full name required")
    if not data.get("phone"):
        raise ValidationError("Phone number required")
    return Tenant.objects.create(
        owner=user,
        workspace=workspace,
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


def create_occupancy(user, workspace, data):
    with transaction.atomic():
        try:
            tenant = Tenant.objects.get(id=data.get("tenant"), workspace=workspace)
        except Tenant.DoesNotExist:
            raise ValidationError("Tenant not found")

        unit_id = data.get("unit")
        subunit_id = data.get("subunit")
        if not unit_id and not subunit_id:
            raise ValidationError("Unit or SubUnit required")

        if subunit_id:
            if unit_id:
                try:
                    unit = Unit.objects.select_for_update().select_related("property").get(
                        id=unit_id, property__workspace=workspace
                    )
                except Unit.DoesNotExist:
                    raise ValidationError("Unit not found")
            else:
                unit_id = SubUnit.objects.filter(
                    id=subunit_id, unit__property__workspace=workspace
                ).values_list("unit_id", flat=True).first()
                if not unit_id:
                    raise ValidationError("SubUnit not found")
                try:
                    unit = Unit.objects.select_for_update().select_related("property").get(
                        id=unit_id, property__workspace=workspace
                    )
                except Unit.DoesNotExist:
                    raise ValidationError("Unit not found")

            try:
                subunit = SubUnit.objects.select_for_update().get(id=subunit_id, unit=unit)
            except SubUnit.DoesNotExist:
                raise ValidationError("SubUnit not found")
            subunit_id = subunit.id
        else:
            try:
                unit = Unit.objects.select_for_update().select_related("property").get(
                    id=unit_id, property__workspace=workspace
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
            check_out_date=data.get("check_out_date"),
            next_due_date=data.get("next_due_date"),
            security_deposit=data.get("security_deposit") or 0,
            deposit_paid=data.get("deposit_paid") or False,
        )

        Invoice.objects.create(
            occupancy=occupancy,
            billing_start=data.get("check_in_date"),
            billing_end=data.get("next_due_date"),
            rent_amount=data.get("rent"),
            charges_amount=Decimal(data.get("charges_amount") or 0),
            due_date=data.get("next_due_date"),
        )
        return occupancy


def get_tenants(workspace):
    return Tenant.objects.filter(workspace=workspace).order_by("id")


def create_charge(user, workspace, data):
    with transaction.atomic():
        try:
            occupancy = Occupancy.objects.select_related("tenant").get(
                id=data.get("occupancy"), tenant__workspace=workspace
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


def get_charges(occupancy_id, workspace):
    return Charge.objects.filter(
        occupancy_id=occupancy_id,
        occupancy__tenant__workspace=workspace,
    )
