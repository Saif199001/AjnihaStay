from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F


class LifecycleProtectedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if "status" in kwargs or "submitted_at" in kwargs or "reviewed_at" in kwargs or "decided_at" in kwargs:
            raise ValidationError("Application lifecycle fields must be changed through the application service")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        protected = {"status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason"}
        if protected.intersection(fields):
            raise ValidationError("Application lifecycle fields must be changed through the application service")
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Applicant(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="applicants")
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["workspace", "created_at"]), models.Index(fields=["workspace", "phone"])]

    def __str__(self):
        return self.full_name


class Application(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_WITHDRAWN = "withdrawn"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"), (STATUS_SUBMITTED, "Submitted"),
        (STATUS_UNDER_REVIEW, "Under review"), (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"), (STATUS_WITHDRAWN, "Withdrawn"),
    )
    ACTIVE_STATUSES = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_UNDER_REVIEW)

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="applications")
    applicant = models.ForeignKey(Applicant, on_delete=models.PROTECT, related_name="applications")
    property = models.ForeignKey("properties.Property", on_delete=models.PROTECT, related_name="applications")
    unit = models.ForeignKey("unit.Unit", on_delete=models.PROTECT, blank=True, null=True, related_name="applications")
    subunit = models.ForeignKey("unit.SubUnit", on_delete=models.PROTECT, blank=True, null=True, related_name="applications")
    requested_check_in_date = models.DateField(blank=True, null=True)
    requested_check_out_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    decided_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, default="")
    withdrawal_reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_applications")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_applications")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LifecycleProtectedQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "status", "created_at"]),
            models.Index(fields=["workspace", "applicant", "property", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_check_out_date__isnull=True) | Q(requested_check_in_date__isnull=True) | Q(requested_check_out_date__gte=F("requested_check_in_date")),
                name="application_dates_valid",
            ),
        ]

    def clean(self):
        if self.requested_check_in_date and self.requested_check_out_date and self.requested_check_out_date < self.requested_check_in_date:
            raise ValidationError("Requested check-out date cannot be before check-in date")
        if self.applicant_id and self.workspace_id and self.applicant.workspace_id != self.workspace_id:
            raise ValidationError("Applicant must belong to the same workspace")
        if self.property_id and self.workspace_id and self.property.workspace_id != self.workspace_id:
            raise ValidationError("Property must belong to the same workspace")
        if self.unit_id:
            if self.unit.property_id != self.property_id or self.unit.property.workspace_id != self.workspace_id:
                raise ValidationError("Unit must belong to the selected property and workspace")
        if self.subunit_id:
            if not self.unit_id or self.subunit.unit_id != self.unit_id:
                raise ValidationError("SubUnit must belong to the selected unit")
            if self.subunit.unit.property.workspace_id != self.workspace_id:
                raise ValidationError("SubUnit must belong to the same workspace")

    def save(self, *args, **kwargs):
        if self.pk and not getattr(self, "_allow_lifecycle_mutation", False):
            previous = type(self).objects.filter(pk=self.pk).values("status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason").first()
            if previous:
                fields = ("status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason")
                if any(getattr(self, field) != previous[field] for field in fields):
                    raise ValidationError("Application lifecycle fields must be changed through the application service")
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Application #{self.pk} - {self.applicant.full_name}"


class ApplicationEvent(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="application_events")
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="history")
    applicant = models.ForeignKey(Applicant, on_delete=models.PROTECT, related_name="application_events")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="application_events")
    occurred_at = models.DateTimeField()
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    event_key = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["workspace", "application", "occurred_at"])]
        constraints = [models.UniqueConstraint(fields=["application", "event_key"], name="application_event_key_uniq")]

    @classmethod
    def append(cls, **kwargs):
        return cls.objects.create(**kwargs)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Application history is immutable")
        if self.application_id and (self.workspace_id != self.application.workspace_id or self.applicant_id != self.application.applicant_id):
            raise ValidationError("Application event relationships must match the application")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Application history is immutable")
