from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F


class LifecycleProtectedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        protected = {"status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason"}
        if protected.intersection(kwargs):
            raise ValidationError("Application lifecycle fields must be changed through the application service")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        protected = {"status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason"}
        if protected.intersection(fields):
            raise ValidationError("Application lifecycle fields must be changed through the application service")
        return super().bulk_update(objs, fields, batch_size=batch_size)


class EventProtectedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Application history is immutable")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Application history is immutable")

    def delete(self):
        raise ValidationError("Application history is immutable")

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        raise ValidationError("Application history must be appended through the application service")


class Applicant(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="applicants")
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "created_at"], name="applicant_ws_created_idx"),
            models.Index(fields=["workspace", "phone"], name="applicant_ws_phone_idx"),
        ]

    def __str__(self):
        return self.full_name


class Application(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_WITHDRAWN = "withdrawn"
    STATUS_CHOICES = ((STATUS_DRAFT, "Draft"), (STATUS_SUBMITTED, "Submitted"), (STATUS_UNDER_REVIEW, "Under review"), (STATUS_APPROVED, "Approved"), (STATUS_REJECTED, "Rejected"), (STATUS_WITHDRAWN, "Withdrawn"))
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
            models.Index(fields=["workspace", "status", "created_at"], name="app_ws_status_created_idx"),
            models.Index(fields=["workspace", "applicant", "property", "status"], name="app_ws_applicant_property_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(requested_check_out_date__isnull=True) | Q(requested_check_in_date__isnull=True) | Q(requested_check_out_date__gte=F("requested_check_in_date")), name="application_dates_valid"),
            models.UniqueConstraint(condition=Q(status__in=["draft", "submitted", "under_review"]), fields=["workspace", "applicant", "property"], name="application_active_applicant_property_uniq"),
        ]

    def clean(self):
        if self.requested_check_in_date and self.requested_check_out_date and self.requested_check_out_date < self.requested_check_in_date:
            raise ValidationError("Requested check-out date cannot be before check-in date")
        if self.applicant_id and self.workspace_id and self.applicant.workspace_id != self.workspace_id:
            raise ValidationError("Applicant must belong to the same workspace")
        if self.property_id and self.workspace_id and self.property.workspace_id != self.workspace_id:
            raise ValidationError("Property must belong to the same workspace")
        if self.unit_id and (self.unit.property_id != self.property_id or self.unit.property.workspace_id != self.workspace_id):
            raise ValidationError("Unit must belong to the selected property and workspace")
        if self.subunit_id:
            if not self.unit_id or self.subunit.unit_id != self.unit_id:
                raise ValidationError("SubUnit must belong to the selected unit")
            if self.subunit.unit.property.workspace_id != self.workspace_id:
                raise ValidationError("SubUnit must belong to the same workspace")

    def save(self, *args, **kwargs):
        lifecycle_fields = ("status", "submitted_at", "reviewed_at", "decided_at", "rejection_reason", "withdrawal_reason")
        if self.pk and not getattr(self, "_allow_lifecycle_mutation", False):
            previous = type(self).objects.filter(pk=self.pk).values(*lifecycle_fields).first()
            if previous and any(getattr(self, field) != previous[field] for field in lifecycle_fields):
                raise ValidationError("Application lifecycle fields must be changed through the application service")
        if not self.pk and self.status != self.STATUS_DRAFT:
            raise ValidationError("New applications must start in draft status")
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

    objects = EventProtectedQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "application", "occurred_at"], name="event_ws_app_occurred_idx"),
        ]
        constraints = [models.UniqueConstraint(fields=["application", "event_key"], name="application_event_key_uniq")]

    @classmethod
    def append(cls, **kwargs):
        event = cls(**kwargs)
        event._allow_event_creation = True
        event.save()
        return event

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Application history is immutable")
        if not getattr(self, "_allow_event_creation", False):
            raise ValidationError("Application history must be appended through the application service")
        if self.application_id and (self.workspace_id != self.application.workspace_id or self.applicant_id != self.application.applicant_id):
            raise ValidationError("Application event relationships must match the application")
        if self.from_status == self.to_status:
            raise ValidationError("Application event must represent a status transition")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Application history is immutable")
