from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from cloudinary.models import CloudinaryField

from unit.models import Unit, SubUnit


class Tenant(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenants")
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
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class Occupancy(models.Model):
    BILLING_TYPES = (("advance", "Advance"), ("arrears", "Arrears"))
    BILLING_CYCLES = (("monthly", "Monthly"), ("daily", "Daily"))
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="occupancies")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="occupancies")
    subunit = models.ForeignKey(SubUnit, on_delete=models.CASCADE, blank=True, null=True, related_name="occupancies")
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
        if self.subunit_id:
            if self.subunit.is_occupied():
                raise ValidationError("SubUnit already occupied")
        elif self.unit.is_occupied():
            raise ValidationError("Unit already occupied")
        existing = Occupancy.objects.filter(is_active=True).exclude(id=self.id)
        existing = existing.filter(subunit_id=self.subunit_id) if self.subunit_id else existing.filter(unit_id=self.unit_id)
        existing = existing.filter(check_in_date__lte=self.check_out_date or self.check_in_date).filter(
            Q(check_out_date__gte=self.check_in_date) | Q(check_out_date__isnull=True)
        )
        if existing.exists():
            raise ValidationError("This unit is already occupied for selected dates")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [models.Index(fields=["is_active"]), models.Index(fields=["check_in_date"]), models.Index(fields=["check_out_date"])]
        constraints = [
            models.CheckConstraint(condition=Q(rent__gte=0), name="occupancy_rent_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="occupancy_deposit_non_negative"),
            models.CheckConstraint(condition=Q(check_out_date__isnull=True) | Q(check_out_date__gte=F("check_in_date")), name="occupancy_checkout_gte_checkin"),
            models.CheckConstraint(condition=Q(next_due_date__gte=F("check_in_date")), name="occupancy_next_due_gte_checkin"),
        ]


class Charge(models.Model):
    CHARGE_TYPES = (("electricity", "Electricity"), ("food", "Food"), ("maintenance", "Maintenance"), ("laundry", "Laundry"), ("custom", "Custom"))
    occupancy = models.ForeignKey(Occupancy, on_delete=models.CASCADE, related_name="charges")
    charge_type = models.CharField(max_length=50, choices=CHARGE_TYPES)
    description = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charge_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Charge amount must be greater than zero")
        if self.occupancy_id and self.charge_date < self.occupancy.check_in_date:
            raise ValidationError("Charge date cannot be before occupancy check-in date")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.charge_type} - {self.amount}"

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="charge_amount_positive")]
