from django.db import models
from unit.models import Unit, SubUnit
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q
from cloudinary.models import CloudinaryField


class Tenant(models.Model):

    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,
    related_name="tenants")

    full_name = models.CharField(max_length=200)

    phone = models.CharField(max_length=15)

    email = models.EmailField(blank=True, null=True)

    profile_photo = CloudinaryField('tenants_photo', blank=True, default=None)

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

    def __str__(self):
        return self.full_name


class Occupancy(models.Model):

    BILLING_TYPES = (
        ("advance", "Advance"),
        ("arrears", "Arrears"),
    )

    BILLING_CYCLES = (
        ("monthly", "Monthly"),
        ("daily", "Daily"),
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="occupancies"
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="occupancies"   # 🔥 FIX
    )

    subunit = models.ForeignKey(
        SubUnit,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="occupancies"   # 🔥 FIX
    )

    allotted_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    related_name="allotted_units"
)

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

        if not self.unit and not self.subunit:
            raise ValidationError("Unit or SubUnit required")

        if self.subunit and self.subunit.unit != self.unit:
            raise ValidationError("SubUnit must belong to selected Unit")

        if self.subunit:
            if self.subunit.is_occupied():
                raise ValidationError("SubUnit already occupied")
        else:
            if self.unit.is_occupied():
                raise ValidationError("Unit already occupied")

        # 🔥 OVERLAP CHECK
        existing = Occupancy.objects.filter(
            is_active=True
        ).exclude(id=self.id)

        if self.subunit:
            existing = existing.filter(subunit=self.subunit)
        else:
            existing = existing.filter(unit=self.unit)

        existing = existing.filter(
            check_in_date__lte=self.check_out_date or self.check_in_date
        ).filter(Q(check_out_date__gte=self.check_in_date) | Q(check_out_date__isnull=True))

        if existing.exists():
            raise ValidationError("This unit is already occupied for selected dates")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["check_in_date"]),
            models.Index(fields=["check_out_date"]),
        ]


class Charge(models.Model):

    CHARGE_TYPES = (
        ("electricity", "Electricity"),
        ("food", "Food"),
        ("maintenance", "Maintenance"),
        ("laundry", "Laundry"),
        ("custom", "Custom"),
    )

    occupancy = models.ForeignKey(
        Occupancy,
        on_delete=models.CASCADE,
        related_name="charges"
    )

    charge_type = models.CharField(max_length=50, choices=CHARGE_TYPES)

    description = models.CharField(max_length=255, blank=True, null=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    charge_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.charge_type} - {self.amount}"