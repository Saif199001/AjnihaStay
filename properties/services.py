from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from workspaces.models import Membership

from .models import Property, PropertyImage, _allow_property_mutation

SUBUNIT_PROPERTY_TYPES = ["pg", "hostel"]
PROPERTY_MUTATION_ROLES = frozenset(
    {
        Membership.ROLE_OWNER,
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
    }
)


def _require_property_mutation_permission(user, workspace):
    if user is None:
        raise PermissionDenied("Property mutation requires workspace membership")

    if not Membership.objects.filter(
        workspace=workspace,
        user=user,
        is_active=True,
        role__in=PROPERTY_MUTATION_ROLES,
    ).exists():
        raise PermissionDenied("Property mutation requires manager-level access")


def create_property(user, workspace, data, files):
    _require_property_mutation_permission(user, workspace)

    if not data.get("name"):
        raise ValidationError("Property name is required")
    if not data.get("property_type"):
        raise ValidationError("Property type is required")

    with transaction.atomic(), _allow_property_mutation():
        property_obj = Property.objects.create(
            owner=user,
            workspace=workspace,
            name=data.get("name"),
            property_type=data.get("property_type"),
            has_subunits=(data.get("property_type") in SUBUNIT_PROPERTY_TYPES),
            description=data.get("description") or "",
            address=data.get("address"),
            city=data.get("city"),
            state=data.get("state"),
            pincode=data.get("pincode"),
            amenities=data.get("amenities") or [],
            thumbnail=files.get("thumbnail"),
        )

        for img in files.getlist("images"):
            PropertyImage.objects.create(property=property_obj, image=img)

    return property_obj
