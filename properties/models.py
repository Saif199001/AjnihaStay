from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField


class Property(models.Model):

    PROPERTY_TYPES = (
        ("pg", "PG"),
        ("hostel", "Hostel"),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="properties"
    )

    name = models.CharField(max_length=200)

    property_type = models.CharField(
        max_length=20,
        choices=PROPERTY_TYPES
    )

    description = models.TextField(blank=True)

    address = models.TextField()

    city = models.CharField(max_length=100)

    state = models.CharField(max_length=100)

    pincode = models.CharField(max_length=10)

    amenities = models.JSONField(default=list, blank=True)

    thumbnail = CloudinaryField('properties', blank=True, default=None)

    is_active = models.BooleanField(default=True)

    is_listed = models.BooleanField(default=False)  # marketplace future

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}"

    def is_owned_by(self, user):
        return self.owner == user


class PropertyImage(models.Model):

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = CloudinaryField('properties', blank=True, default=None)

    caption = models.CharField(max_length=255, blank=True, null=True)

    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.property.name}"