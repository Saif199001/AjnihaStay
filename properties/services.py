from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Property, PropertyImage

SUBUNIT_PROPERTY_TYPES = ["pg", "hostel"]


def create_property(user, workspace, data, files):
    if not data.get("name"):
        raise ValidationError("Property name is required")
    if not data.get("property_type"):
        raise ValidationError("Property type is required")

    with transaction.atomic():
        property_obj = Property.objects.create(
            owner=user,
            workspace=workspace,
            name=data.get("name"),
            property_type=data.get("property_type"),
            has_subunits=(data.get("property_type") in SUBUNIT_PROPERTY_TYPES),
            description=data.get("description"),
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
