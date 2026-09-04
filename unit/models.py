from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from properties.models import Property
from cloudinary.models import CloudinaryField


class Unit(models.Model):

    UNIT_TYPES = (
        ("room", "Room"),
        ("flat", "Flat"),
        ("shop", "Shop"),
        ("office", "Office"),
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="units"
    )

    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES)

    unit_number = models.CharField(max_length=50)

    description = models.TextField(blank=True, null=True)

    amenities = models.JSONField(default=list, blank=True)

    rent = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    capacity = models.IntegerField(default=1)

    is_active = models.BooleanField(default=True)

    is_available_for_public = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["unit_number"]
        unique_together = ["property", "unit_number"]
        indexes = [
            models.Index(fields=["property"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gte=1), name="unit_capacity_positive"),
            models.CheckConstraint(condition=Q(rent__isnull=True) | Q(rent__gte=0), name="unit_rent_non_negative"),
        ]

    def __str__(self):
        return f"{self.property.name if self.property else 'No Property'} - {self.unit_number}"

    def clean(self):
        if self.capacity < 1:
            raise ValidationError("Unit capacity must be at least 1")
        if self.rent is not None and self.rent < 0:
            raise ValidationError("Unit rent cannot be negative")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def is_occupied(self):
        from tenant.models import Occupancy

        return Occupancy.objects.filter(
            unit=self,
            is_active=True
        ).exists()


class SubUnit(models.Model):

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="subunits"
    )

    subunit_number = models.CharField(max_length=50)

    rent = models.DecimalField(max_digits=10, decimal_places=2)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["unit", "subunit_number"]
        constraints = [
            models.CheckConstraint(condition=Q(rent__gte=0), name="subunit_rent_non_negative"),
        ]

    def __str__(self):
        return f"{self.unit} - {self.subunit_number}"

    def clean(self):
        if self.rent < 0:
            raise ValidationError("SubUnit rent cannot be negative")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def is_occupied(self):
        from tenant.models import Occupancy

        return Occupancy.objects.filter(
            subunit=self,
            is_active=True
        ).exists()


class UnitImage(models.Model):

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = CloudinaryField('units', blank=True, default=None)

    caption = models.CharField(max_length=255, blank=True, null=True)

    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.unit}"
