from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class LeaseLifecycleEvent(models.Model):
    EVENT_CREATED = "created"
    EVENT_PENDING_SIGNATURE = "pending_signature"
    EVENT_ACTIVATED = "activated"
    EVENT_RENEWED = "renewed"
    EVENT_NOTICE = "notice"
    EVENT_EXPIRED = "expired"
    EVENT_TERMINATED = "terminated"
    EVENT_CANCELLED = "cancelled"

    EVENT_CHOICES = (
        (EVENT_CREATED, "Created"),
        (EVENT_PENDING_SIGNATURE, "Pending Signature"),
        (EVENT_ACTIVATED, "Activated"),
        (EVENT_RENEWED, "Renewed"),
        (EVENT_NOTICE, "Notice"),
        (EVENT_EXPIRED, "Expired"),
        (EVENT_TERMINATED, "Terminated"),
        (EVENT_CANCELLED, "Cancelled"),
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="lease_lifecycle_events",
    )
    lease = models.ForeignKey(
        "leasing.Lease",
        on_delete=models.PROTECT,
        related_name="lifecycle_events",
    )
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES)
    occurred_at = models.DateTimeField()
    effective_date = models.DateField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lease_lifecycle_events",
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "lease"], name="lease_evt_ws_lease_idx"),
            models.Index(fields=["workspace", "event_type"], name="lease_evt_ws_type_idx"),
            models.Index(fields=["lease", "occurred_at"], name="lease_evt_lease_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(event_type__in=[
                    "created",
                    "pending_signature",
                    "activated",
                    "renewed",
                    "notice",
                    "expired",
                    "terminated",
                    "cancelled",
                ]),
                name="lease_evt_type_valid",
            ),
        ]

    def clean(self):
        if self.lease_id and self.workspace_id:
            if self.lease.workspace_id != self.workspace_id:
                raise ValidationError("Lifecycle event must belong to the same workspace as the lease")
        if self.actor_id and self.workspace_id:
            from workspaces.models import Membership

            if not Membership.objects.filter(
                workspace_id=self.workspace_id,
                user_id=self.actor_id,
                is_active=True,
            ).exists():
                raise ValidationError("Lifecycle event actor must be an active workspace member")

    def save(self, *args, **kwargs):
        self.clean()
        if self.pk:
            raise ValidationError("Lease lifecycle events are immutable")
        super().save(*args, **kwargs)


class LeaseNotice(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_WITHDRAWN = "withdrawn"
    STATUS_EFFECTIVE = "effective"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_WITHDRAWN, "Withdrawn"),
        (STATUS_EFFECTIVE, "Effective"),
        (STATUS_COMPLETED, "Completed"),
    )

    TYPE_TERMINATION = "termination"
    TYPE_NON_RENEWAL = "non_renewal"
    TYPE_OTHER = "other"
    TYPE_CHOICES = (
        (TYPE_TERMINATION, "Termination"),
        (TYPE_NON_RENEWAL, "Non Renewal"),
        (TYPE_OTHER, "Other"),
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="lease_notices",
    )
    lease = models.ForeignKey(
        "leasing.Lease",
        on_delete=models.PROTECT,
        related_name="notices",
    )
    notice_date = models.DateField()
    effective_date = models.DateField()
    notice_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lease_notices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "lease"], name="lease_note_ws_lease_idx"),
            models.Index(fields=["workspace", "effective_date"], name="lease_note_ws_eff_idx"),
            models.Index(fields=["workspace", "status"], name="lease_note_ws_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_date__gte=models.F("notice_date")),
                name="lease_note_eff_gte_notice",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "issued", "withdrawn", "effective", "completed"]),
                name="lease_note_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(notice_type__in=["termination", "non_renewal", "other"]),
                name="lease_note_type_valid",
            ),
        ]

    def clean(self):
        if not self.reason or not self.reason.strip():
            raise ValidationError("Notice reason is required")
        if self.lease_id and self.workspace_id:
            if self.lease.workspace_id != self.workspace_id:
                raise ValidationError("Notice must belong to the same workspace as the lease")
        if self.created_by_id and self.workspace_id:
            from workspaces.models import Membership

            if not Membership.objects.filter(
                workspace_id=self.workspace_id,
                user_id=self.created_by_id,
                is_active=True,
            ).exists():
                raise ValidationError("Notice creator must be an active workspace member")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
