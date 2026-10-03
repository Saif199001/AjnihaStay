from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from properties.models import Property
from workspaces.models import Membership, Workspace
from .models import SubUnit, Unit, _allow_unit_mutation


def _ensure_workspace_active(workspace):
    if workspace is None:
        raise ValidationError("Workspace is required")
    if not Workspace.objects.filter(pk=workspace.pk, is_active=True).exists():
        raise ValidationError("Workspace is archived")


UNIT_MUTATION_ROLES = frozenset(
    {
        Membership.ROLE_OWNER,
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
    }
)


def _require_unit_mutation_permission(user, workspace):
    if user is None:
        raise PermissionDenied("Unit mutation requires workspace membership")

    if not Membership.objects.filter(
        workspace=workspace,
        user=user,
        is_active=True,
        role__in=UNIT_MUTATION_ROLES,
    ).exists():
        raise PermissionDenied("Unit mutation requires manager-level access")


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
    _ensure_workspace_active(workspace)
    property_id = _optional_positive_id(property_id, "property")
    units = Unit.objects.filter(property__workspace=workspace)
    if property_id is not None:
        units = units.filter(property_id=property_id)
    return units


def create_unit(user, workspace, data):
    _ensure_workspace_active(workspace)
    _require_unit_mutation_permission(user, workspace)

    property_value = data.get("property")
    property_id = getattr(property_value, "id", property_value)
    try:
        property_obj = Property.objects.get(id=property_id, workspace=workspace)
    except (Property.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Property not found")

    if not data.get("unit_number"):
        raise ValidationError("Unit number required")

    rent_value = data.get("rent")
    if rent_value in (None, ""):
        raise ValidationError("Rent is required")

    try:
        rent = Decimal(rent_value)
        capacity = int(data.get("capacity") or 1)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid unit values")

    if rent <= 0:
        raise ValidationError("Rent must be greater than 0")
    if capacity <= 0:
        raise ValidationError("Capacity must be greater than 0")

    with _allow_unit_mutation():
        return Unit.objects.create(
            property=property_obj,
            unit_number=data.get("unit_number"),
            unit_type=data.get("unit_type"),
            rent=rent,
            capacity=capacity,
            description=data.get("description"),
        )


def create_subunit(user, workspace, data):
    _ensure_workspace_active(workspace)
    _require_unit_mutation_permission(user, workspace)

    unit_value = data.get("unit")
    unit_id = getattr(unit_value, "id", unit_value)

    with transaction.atomic():
        try:
            unit = Unit.objects.select_for_update().select_related("property").get(
                id=unit_id, property__workspace=workspace
            )
        except (Unit.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Unit not found")

        if not unit.property.has_subunits:
            raise ValidationError("SubUnit is not allowed for this property type")

        if unit.rent is None or unit.rent <= 0:
            raise ValidationError("Unit rent must be greater than 0")

        rent_value = data.get("rent")
        if rent_value in (None, ""):
            raise ValidationError("Rent is required")

        try:
            new_rent = Decimal(rent_value)
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError("Invalid rent")
        if new_rent <= 0:
            raise ValidationError("Rent must be greater than 0")

        if unit.subunits.filter(is_active=True).count() >= unit.capacity:
            raise ValidationError("Capacity full")

        existing_total = sum(
            (s.rent for s in unit.subunits.filter(is_active=True)),
            Decimal("0"),
        )
        if existing_total + new_rent > unit.rent:
            raise ValidationError("Total rent exceeded")

        with _allow_unit_mutation():
            return SubUnit.objects.create(
                unit=unit,
                subunit_number=data.get("subunit_number"),
                rent=new_rent,
            )
