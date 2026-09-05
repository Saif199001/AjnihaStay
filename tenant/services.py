from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.models import Invoice
from unit.models import SubUnit, Unit
from .models import Charge, Occupancy, Tenant


DEFAULT_BILLING_TYPE = "advance"
DEFAULT_BILLING_CYCLE = "monthly"


def _billing_value(data, field_name, default, allowed_values):
    value = data.get(field_name)
    if value in (None, ""):
        value = default
    if value not in allowed_values:
        raise ValidationError(f"Invalid {field_name}")
    return value


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
        tenant_value = data.get("tenant")
        tenant_id = tenant_value.id if isinstance(tenant_value, Tenant) else tenant_value
        try:
            tenant = Tenant.objects.get(id=tenant_id, workspace=workspace)
        except (Tenant.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Tenant not found")

        unit_value = data.get("unit")
        unit_id = unit_value.id if isinstance(unit_value, Unit) else unit_value
        subunit_value = data.get("subunit")
        subunit_id = subunit_value.id if isinstance(subunit_value, SubUnit) else subunit_value

        if not unit_id and not subunit_id:
            raise ValidationError("Unit or SubUnit required")

        if subunit_id:
            if unit_id:
                try:
                    unit = Unit.objects.select_for_update().select_related("property").get(
                        id=unit_id, property__workspace=workspace
                    )
                except (Unit.DoesNotExist, TypeError, ValueError):
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
                except (Unit.DoesNotExist, TypeError, ValueError):
                    raise ValidationError("Unit not found")

            try:
                subunit = SubUnit.objects.select_for_update().get(id=subunit_id, unit=unit)
            except (SubUnit.DoesNotExist, TypeError, ValueError):
                raise ValidationError("SubUnit not found")
            subunit_id = subunit.id
        else:
            try:
                unit = Unit.objects.select_for_update().select_related("property").get(
                    id=unit_id, property__workspace=workspace
                )
            except (Unit.DoesNotExist, TypeError, ValueError):
                raise ValidationError("Unit not found")

        billing_type = _billing_value(
            data,
            "billing_type",
            DEFAULT_BILLING_TYPE,
            {value for value, _ in Occupancy.BILLING_TYPES},
        )
        billing_cycle = _billing_value(
            data,
            "billing_cycle",
            DEFAULT_BILLING_CYCLE,
            {value for value, _ in Occupancy.BILLING_CYCLES},
        )

        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            subunit_id=subunit_id,
            allotted_by=user,
            rent=data.get("rent"),
            billing_type=billing_type,
            billing_cycle=billing_cycle,
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
        occupancy_value = data.get("occupancy")
        if isinstance(occupancy_value, Occupancy):
            occupancy_id = occupancy_value.id
        else:
            occupancy_id = occupancy_value

        try:
            occupancy = Occupancy.objects.select_related("tenant").get(
                id=occupancy_id, tenant__workspace=workspace
            )
        except (Occupancy.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Occupancy not found")

        invoice = occupancy.invoices.select_for_update().filter(status="pending").last()
        if not invoice:
            raise ValidationError("No active invoice found")

        charge = Charge.objects.create(
            occupancy=occupancy,
            charge_type=data.get("charge_type"),
            description=data.get("description"),
            amount=data.get("amount"),
            charge_date=data.get("charge_date"),
        )

        invoice.charges_amount += charge.amount
        invoice.total_amount = invoice.rent_amount + invoice.charges_amount
        invoice.save()
        return charge


def _optional_positive_id(value, field_name):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name} ID")
    if parsed <= 0:
        raise ValidationError(f"Invalid {field_name} ID")
    return parsed


def get_charges(occupancy_id, workspace):
    occupancy_id = _optional_positive_id(occupancy_id, "occupancy")
    return Charge.objects.filter(
        occupancy_id=occupancy_id,
        occupancy__tenant__workspace=workspace,
    )
