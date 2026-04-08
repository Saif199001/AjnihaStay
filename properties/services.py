from .models import Property


def get_properties(user):
    return Property.objects.filter(owner=user)


def create_property(user, data, files):

    property = Property.objects.create(
        owner=user,
        name=data.get("name"),
        property_type=data.get("property_type"),
        address=data.get("address"),
        city=data.get("city"),
        state=data.get("state"),
        pincode=data.get("pincode"),
        thumbnail=files.get("thumbnail")   # 🔥 ADD THIS
    )

    return property