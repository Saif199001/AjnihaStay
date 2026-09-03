from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from properties.models import Property
from .models import SubUnit, Unit


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


def get_units(workspace, property_id=None):
    property_id = _optional_positive_id(property_id, "property")
    units = Unit.objects.filter(property__workspace=workspace)
    if property_id is not None:
        units = units.filter(property_id=property_id)
    return units


def create_unit(workspace, data):
    property_value = data.get("property")
    property_id = getattr(property_value, "id", property_value)
    try:
        property_obj = Property.objects.get(id=property_id, workspace=workspace)
    except (Property.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Property not found")

    if not data.get("unit_number"):
        raise ValidationError("Unit number required")

    try:
        rent = Decimal(data.get("rent") or 0)
        capacity = int(data.get("capacity") or 1)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid unit values")

    if rent < 0:
        raise ValidationError("Rent cannot be negative")
    if capacity <= 0:
        raise ValidationError("Capacity must be greater than 0")

    return Unit.objects.create(
        property=property_obj,
        unit_number=data.get("unit_number"),
        unit_type=data.get("unit_type"),
        rent=rent,
        capacity=capacity,
        description=data.get("description"),
    )


def create_subunit(workspace, data):
    unit_value = data.get("unit")
    unit_id = getattr(unit_value, "id", unit_value)

    with transaction.atomic():
        try:
            unit = Unit.objects.select_for_update().select_related("property").get(
                id=unit_id, property__workspace=workspace
            )
        except (Unit.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Unit not found")

        if not unit.rent:
            raise ValidationError("Unit rent must be set")

        try:
            new_rent = Decimal(data.get("rent") or 0)
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError("Invalid rent")
        if new_rent <= 0:
            raise ValidationError("Invalid rent")

        if unit.subunits.filter(is_active=True).count() >= unit.capacity:
            raise ValidationError("Capacity full")

        existing_total = sum(
            (s.rent for s in unit.subunits.filter(is_active=True)),
            Decimal("0"),
        )
        if existing_total + new_rent > unit.rent:
            raise ValidationError("Total rent exceeded")

        return SubUnit.objects.create(
            unit=unit,
            subunit_number=data.get("subunit_number"),
            rent=new_rent,
        )
