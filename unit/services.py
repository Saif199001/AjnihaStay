from .models import Unit, SubUnit
from properties.models import Property
from django.core.exceptions import ValidationError
from decimal import Decimal


def get_units(user, property_id=None):
    units = Unit.objects.filter(property__owner=user)

    if property_id:
        units = units.filter(property_id=property_id)

    return units


def create_unit(user, data):
    try:
        property = Property.objects.get(id=data.get("property"))
    except Property.DoesNotExist:
        raise ValidationError("Property not found")

    if property.owner != user:
        raise ValidationError("Unauthorized")

    if not data.get("unit_number"):
        raise ValidationError("Unit number required")

    return Unit.objects.create(
        property=property,
        unit_number=data.get("unit_number"),
        unit_type=data.get("unit_type"),
        rent=Decimal(data.get("rent") or 0),
        capacity=int(data.get("capacity") or 1),
        description=data.get("description"),
    )


# 🔥 SUBUNIT LOGIC (IMPORTANT)
def create_subunit(user, data):

    try:
        unit = Unit.objects.get(id=data.get("unit"))
    except Unit.DoesNotExist:
        raise ValidationError("Unit not found")

    # 🔐 ownership check
    if unit.property.owner != user:
        raise ValidationError("Unauthorized")

    if not unit.rent:
        raise ValidationError("Unit rent must be set")

    new_rent = Decimal(data.get("rent") or 0)

    if new_rent <= 0:
        raise ValidationError("Invalid rent")

    # capacity check
    if unit.subunits.count() >= unit.capacity:
        raise ValidationError("Capacity full")

    existing_total = sum(s.rent for s in unit.subunits.all())

    if existing_total + new_rent > unit.rent:
        raise ValidationError("Total rent exceeded")

    return SubUnit.objects.create(
        unit=unit,
        subunit_number=data.get("subunit_number"),
        rent=new_rent
    )