from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import Q
from cloudinary.models import CloudinaryField


_PROPERTY_MUTATION_ALLOWED = ContextVar(
    "property_mutation_allowed",
    default=False,
)


@contextmanager
def _allow_property_mutation():
    token = _PROPERTY_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _PROPERTY_MUTATION_ALLOWED.reset(token)


class PropertyQuerySet(models.QuerySet):
    def _ensure_mutation_allowed(self):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property state must be changed through the canonical property service."
            )

    def update(self, **kwargs):
        self._ensure_mutation_allowed()
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        self._ensure_mutation_allowed()
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        if objs:
            self._ensure_mutation_allowed()
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
        )

    def delete(self):
        self._ensure_mutation_allowed()
        return super().delete()


SUBUNIT_PROPERTY_TYPES = ["pg", "hostel"]


class Property(models.Model):
    PROPERTY_TYPES = (
        ("pg", "PG"),
        ("hostel", "Hostel"),
        ("shop", "Shop"),
        ("flat", "Flat"),
        ("office", "Office"),
        ("building", "Building"),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="properties",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="workspace_properties",
    )
    name = models.CharField(max_length=200)
    has_subunits = models.BooleanField(default=False)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES)
    description = models.TextField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    amenities = models.JSONField(default=list, blank=True)
    thumbnail = CloudinaryField("properties", blank=True, null=True, default=None)
    is_active = models.BooleanField(default=True)
    is_listed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city"]),
            models.Index(fields=["state"]),
            models.Index(fields=["property_type"]),
            models.Index(fields=["workspace", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(property_type__in=SUBUNIT_PROPERTY_TYPES, has_subunits=True)
                    | Q(property_type__in=["shop", "flat", "office", "building"], has_subunits=False)
                ),
                name="property_type_has_subunits_consistent",
            ),
        ]

    def clean(self):
        expected_has_subunits = self.property_type in SUBUNIT_PROPERTY_TYPES
        if self.has_subunits != expected_has_subunits:
            raise ValidationError(
                "has_subunits is derived from property_type and cannot be inconsistent"
            )

        if self.owner_id and self.workspace_id:
            from workspaces.models import Membership

            if not Membership.objects.filter(
                workspace_id=self.workspace_id,
                user_id=self.owner_id,
                is_active=True,
            ).exists():
                raise ValidationError("Property owner must be an active workspace member")

    objects = PropertyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property state must be changed through the canonical property service."
            )
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property state must be changed through the canonical property service."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.city}"

    def is_owned_by(self, user):
        return self.owner == user


class PropertyImageQuerySet(models.QuerySet):
    def _ensure_mutation_allowed(self):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property image state must be changed through the canonical property service."
            )

    def update(self, **kwargs):
        self._ensure_mutation_allowed()
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        self._ensure_mutation_allowed()
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        if objs:
            self._ensure_mutation_allowed()
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
        )

    def delete(self):
        self._ensure_mutation_allowed()
        return super().delete()


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = CloudinaryField("properties", blank=True, null=True, default=None)
    caption = models.CharField(max_length=255, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PropertyImageQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property image state must be changed through the canonical property service."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _PROPERTY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Property image state must be changed through the canonical property service."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.property.name}"
