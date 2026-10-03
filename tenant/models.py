from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import F, Q
from cloudinary.models import CloudinaryField

from unit.models import Unit, SubUnit


_TENANT_MUTATION_ALLOWED = ContextVar(
    "tenant_mutation_allowed",
    default=False,
)

_OCCUPANCY_MUTATION_ALLOWED = ContextVar(
    "occupancy_mutation_allowed",
    default=False,
)

_CHARGE_MUTATION_ALLOWED = ContextVar(
    "charge_mutation_allowed",
    default=False,
)


@contextmanager
def _allow_tenant_mutation():
    token = _TENANT_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _TENANT_MUTATION_ALLOWED.reset(token)


@contextmanager
def _allow_occupancy_mutation():
    token = _OCCUPANCY_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _OCCUPANCY_MUTATION_ALLOWED.reset(token)


@contextmanager
def _allow_charge_mutation():
    token = _CHARGE_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _CHARGE_MUTATION_ALLOWED.reset(token)


class TenantQuerySet(models.QuerySet):
    def _ensure_mutation_allowed(self):
        if not _TENANT_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Tenant state must be changed through the canonical tenant service."
            )

    def update(self, **kwargs):
        if "workspace" in kwargs or "workspace_id" in kwargs:
            raise PermissionDenied("Tenant workspace cannot be reassigned.")
        self._ensure_mutation_allowed()
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if "workspace" in fields or "workspace_id" in fields:
            raise PermissionDenied("Tenant workspace cannot be reassigned.")
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


class Tenant(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tenants")
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="workspace_tenants")
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    profile_photo = CloudinaryField("tenants_photo", blank=True, null=True, default=None)
    nationality = models.CharField(max_length=100, default="Indian")
    id_proof_type = models.CharField(max_length=50, blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_document = models.FileField(upload_to="tenant_documents/", blank=True, null=True)
    permanent_address = models.TextField()
    district = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pin_code = models.CharField(max_length=10, blank=True, null=True)
    emergency_contact = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["workspace", "created_at"])]

    def clean(self):
        if self.owner_id and self.workspace_id:
            from workspaces.models import Membership

            if not Membership.objects.filter(
                workspace_id=self.workspace_id,
                user_id=self.owner_id,
                is_active=True,
            ).exists():
                raise ValidationError("Tenant owner must be an active workspace member")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original_workspace_id = type(self).objects.filter(pk=self.pk).values_list(
                "workspace_id", flat=True
            ).first()
            if original_workspace_id is not None and original_workspace_id != self.workspace_id:
                raise PermissionDenied("Tenant workspace cannot be reassigned.")
        if not _TENANT_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Tenant state must be changed through the canonical tenant service."
            )
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _TENANT_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Tenant state must be changed through the canonical tenant service."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.full_name


class OccupancyQuerySet(models.QuerySet):
    def _ensure_mutation_allowed(self):
        if not _OCCUPANCY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Occupancy state must be changed through the canonical occupancy service."
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


class Occupancy(models.Model):
    BILLING_TYPES = (("advance", "Advance"), ("arrears", "Arrears"))
    BILLING_CYCLES = (("monthly", "Monthly"), ("daily", "Daily"))
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="occupancies")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="occupancies")
    subunit = models.ForeignKey(SubUnit, on_delete=models.PROTECT, blank=True, null=True, related_name="occupancies")
    allotted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="allotted_units")
    rent = models.DecimalField(max_digits=10, decimal_places=2)
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPES, default="advance")
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLES, default="monthly")
    check_in_date = models.DateField()
    check_out_date = models.DateField(blank=True, null=True)
    next_due_date = models.DateField()
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_paid = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OccupancyQuerySet.as_manager()

    def __str__(self):
        return f"{self.tenant.full_name} - {self.unit.unit_number}"

    def clean(self):
        if not self.unit_id and not self.subunit_id:
            raise ValidationError("Unit or SubUnit required")
        if self.subunit_id and self.unit_id and self.subunit.unit_id != self.unit_id:
            raise ValidationError("SubUnit must belong to selected Unit")
        if self.tenant.workspace_id != self.unit.property.workspace_id:
            raise ValidationError("Tenant and Unit must belong to the same workspace")
        if self.allotted_by_id:
            from workspaces.models import Membership

            if not Membership.objects.filter(
                workspace_id=self.tenant.workspace_id,
                user_id=self.allotted_by_id,
                is_active=True,
            ).exists():
                raise ValidationError("Allotted by user must be an active workspace member")
        if self.rent < 0:
            raise ValidationError("Rent cannot be negative")
        if self.security_deposit < 0:
            raise ValidationError("Security deposit cannot be negative")
        if self.check_out_date and self.check_out_date < self.check_in_date:
            raise ValidationError("Check-out date cannot be before check-in date")
        if self.next_due_date < self.check_in_date:
            raise ValidationError("Next due date cannot be before check-in date")

        overlap_filter = Q(check_in_date__lte=self.check_out_date or self.check_in_date) & (
            Q(check_out_date__gte=self.check_in_date) | Q(check_out_date__isnull=True)
        )
        existing = Occupancy.objects.filter(is_active=True).exclude(id=self.id).filter(overlap_filter)

        if self.subunit_id:
            if not self.subunit.is_active:
                raise ValidationError("SubUnit is inactive")
            if existing.filter(subunit_id=self.subunit_id).exists():
                raise ValidationError("SubUnit is already occupied for selected dates")
        else:
            if not self.unit.is_active:
                raise ValidationError("Unit is inactive")
            overlapping_count = existing.filter(unit_id=self.unit_id, subunit_id__isnull=True).count()
            if overlapping_count >= self.unit.capacity:
                raise ValidationError("Unit capacity is full for selected dates")

    def save(self, *args, **kwargs):
        if not _OCCUPANCY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Occupancy state must be changed through the canonical occupancy service."
            )
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _OCCUPANCY_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Occupancy state must be changed through the canonical occupancy service."
            )
        return super().delete(*args, **kwargs)

    class Meta:
        indexes = [models.Index(fields=["is_active"]), models.Index(fields=["check_in_date"]), models.Index(fields=["check_out_date"])]
        constraints = [
            models.CheckConstraint(condition=Q(rent__gte=0), name="occupancy_rent_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="occupancy_deposit_non_negative"),
            models.CheckConstraint(condition=Q(check_out_date__isnull=True) | Q(check_out_date__gte=F("check_in_date")), name="occupancy_checkout_gte_checkin"),
            models.CheckConstraint(condition=Q(next_due_date__gte=F("check_in_date")), name="occupancy_next_due_gte_checkin"),
        ]


class ChargeQuerySet(models.QuerySet):
    def _ensure_mutation_allowed(self):
        if not _CHARGE_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Charge state must be changed through the canonical charge service."
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


class Charge(models.Model):
    CHARGE_TYPES = (("electricity", "Electricity"), ("food", "Food"), ("maintenance", "Maintenance"), ("laundry", "Laundry"), ("custom", "Custom"))
    occupancy = models.ForeignKey(Occupancy, on_delete=models.PROTECT, related_name="charges")
    billing_schedule = models.ForeignKey(
        "payments.BillingSchedule",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="charges",
    )
    charge_type = models.CharField(max_length=50, choices=CHARGE_TYPES)
    description = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charge_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ChargeQuerySet.as_manager()

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Charge amount must be greater than zero")
        if self.occupancy_id and self.charge_date < self.occupancy.check_in_date:
            raise ValidationError("Charge date cannot be before occupancy check-in date")
        if self.billing_schedule_id:
            if self.billing_schedule.occupancy_id != self.occupancy_id:
                raise ValidationError("Billing schedule must belong to the charge occupancy")

    def save(self, *args, **kwargs):
        if not _CHARGE_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Charge state must be changed through the canonical charge service."
            )
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _CHARGE_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Charge state must be changed through the canonical charge service."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.charge_type} - {self.amount}"

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="charge_amount_positive"),
            models.UniqueConstraint(
                fields=["billing_schedule", "charge_date"],
                condition=Q(billing_schedule__isnull=False),
                name="charge_schedule_date_unique",
            ),
        ]
