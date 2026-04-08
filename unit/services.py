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
    property = Property.objects.get(id=data.get("property"))

    return Unit.objects.create(
        property=property,
        unit_number=data.get("unit_number"),
        unit_type=data.get("unit_type"),
        rent=Decimal(data.get("rent") or 0),
        capacity=int(data.get("capacity") or 1),
    )


# 🔥 SUBUNIT LOGIC (IMPORTANT)
def create_subunit(data):
    unit = Unit.objects.get(id=data.get("unit"))

    new_rent = Decimal(data.get("rent") or 0)

    # capacity check
    if unit.subunits.count() >= unit.capacity:
        raise ValidationError("Capacity full. Cannot add more beds")

    # rent check
    existing_total = sum(s.rent for s in unit.subunits.all())

    if existing_total + new_rent > unit.rent:
        raise ValidationError("Total bed rent exceeds unit rent")

    return SubUnit.objects.create(
        unit=unit,
        subunit_number=data.get("subunit_number"),
        rent=new_rent
    )