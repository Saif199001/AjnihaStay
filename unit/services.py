from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

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
    try:
        property_obj = Property.objects.get(id=data.get("property"), workspace=workspace)
    except Property.DoesNotExist:
        raise ValidationError("Property not found")

    if not data.get("unit_number"):
        raise ValidationError("Unit number required")

    try:
        rent = Decimal(data.get("rent") or 0)
        capacity = int(data.get("capacity") or 1)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid unit values")

    return Unit.objects.create(
        property=property_obj,
        unit_number=data.get("unit_number"),
        unit_type=data.get("unit_type"),
        rent=rent,
        capacity=capacity,
        description=data.get("description"),
    )


def create_subunit(workspace, data):
    try:
        unit = Unit.objects.select_related("property").get(
            id=data.get("unit"), property__workspace=workspace
        )
    except Unit.DoesNotExist:
        raise ValidationError("Unit not found")

    if not unit.rent:
        raise ValidationError("Unit rent must be set")

    try:
        new_rent = Decimal(data.get("rent") or 0)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid rent")
    if new_rent <= 0:
        raise ValidationError("Invalid rent")

    if unit.subunits.count() >= unit.capacity:
        raise ValidationError("Capacity full")

    existing_total = sum(s.rent for s in unit.subunits.all())
    if existing_total + new_rent > unit.rent:
        raise ValidationError("Total rent exceeded")

    return SubUnit.objects.create(
        unit=unit,
        subunit_number=data.get("subunit_number"),
        rent=new_rent,
    )
