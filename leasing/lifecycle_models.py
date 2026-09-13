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

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="lease_lifecycle_events")
    lease = models.ForeignKey("leasing.Lease", on_delete=models.PROTECT, related_name="lifecycle_events")
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES)
    event_key = models.CharField(max_length=100, null=True, blank=True)
    occurred_at = models.DateTimeField()
    effective_date = models.DateField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lease_lifecycle_events", null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "lease"], name="lease_evt_ws_lease_idx"),
            models.Index(fields=["workspace", "event_type"], name="lease_evt_ws_type_idx"),
            models.Index(fields=["lease", "occurred_at"], name="lease_evt_lease_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(event_type__in=["created", "pending_signature", "activated", "renewed", "notice", "expired", "terminated", "cancelled"]), name="lease_evt_type_valid"),
            models.UniqueConstraint(fields=["lease", "event_key"], condition=Q(event_key__isnull=False), name="lease_evt_lease_key_uniq"),
        ]

    def clean(self):
        if self.lease_id and self.workspace_id and self.lease.workspace_id != self.workspace_id:
            raise ValidationError("Lifecycle event must belong to the same workspace as the lease")
        if self.actor_id and self.workspace_id:
            from workspaces.models import Membership
            if not Membership.objects.filter(workspace_id=self.workspace_id, user_id=self.actor_id, is_active=True).exists():
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
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="lease_notices")
    lease = models.ForeignKey("leasing.Lease", on_delete=models.PROTECT, related_name="notices")
    notice_date = models.DateField()
    effective_date = models.DateField()
    notice_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lease_notices_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "lease"], name="lease_note_ws_lease_idx"),
            models.Index(fields=["workspace", "effective_date"], name="lease_note_ws_eff_idx"),
            models.Index(fields=["workspace", "status"], name="lease_note_ws_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(effective_date__gte=models.F("notice_date")), name="lease_note_eff_gte_notice"),
            models.CheckConstraint(condition=Q(status__in=["draft", "issued", "withdrawn", "effective", "completed"]), name="lease_note_status_valid"),
            models.CheckConstraint(condition=Q(notice_type__in=["termination", "non_renewal", "other"]), name="lease_note_type_valid"),
        ]

    def clean(self):
        if not self.reason or not self.reason.strip():
            raise ValidationError("Notice reason is required")
        if self.lease_id and self.workspace_id and self.lease.workspace_id != self.workspace_id:
            raise ValidationError("Notice must belong to the same workspace as the lease")
        if self.created_by_id and self.workspace_id:
            from workspaces.models import Membership
            if not Membership.objects.filter(workspace_id=self.workspace_id, user_id=self.created_by_id, is_active=True).exists():
                raise ValidationError("Notice creator must be an active workspace member")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class LeaseRenewal(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="lease_renewals")
    source_lease = models.ForeignKey("leasing.Lease", on_delete=models.PROTECT, related_name="renewals")
    renewal_number = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notice_period_days = models.PositiveIntegerField(default=0)
    terms = models.JSONField(default=dict, blank=True)
    agreement_reference = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lease_renewals_created")
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    successor_version = models.OneToOneField(
        "LeaseContractVersion",
        on_delete=models.PROTECT,
        related_name="source_renewal",
        null=True,
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "source_lease"], name="lease_renew_ws_src_idx"),
            models.Index(fields=["workspace", "start_date"], name="lease_renew_ws_start_idx"),
            models.Index(fields=["workspace", "status"], name="lease_renew_ws_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["source_lease", "renewal_number"], name="lease_renew_src_num_uniq"),
            models.CheckConstraint(condition=Q(renewal_number__gte=1), name="lease_renew_num_positive"),
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="lease_renew_end_gte_start"),
            models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_renew_rent_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_renew_dep_non_negative"),
            models.CheckConstraint(condition=Q(status__in=["draft", "confirmed", "cancelled"]), name="lease_renew_status_valid"),
        ]

    def clean(self):
        if self.source_lease_id and self.workspace_id and self.source_lease.workspace_id != self.workspace_id:
            raise ValidationError("Renewal must belong to the same workspace as the source lease")
        if self.successor_version_id and self.successor_version.workspace_id != self.workspace_id:
            raise ValidationError("Renewal successor version must belong to the same workspace")
        if self.created_by_id and self.workspace_id:
            from workspaces.models import Membership
            if not Membership.objects.filter(workspace_id=self.workspace_id, user_id=self.created_by_id, is_active=True).exists():
                raise ValidationError("Renewal creator must be an active workspace member")

    def save(self, *args, **kwargs):
        self.clean()
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous_status == self.STATUS_CONFIRMED:
                raise ValidationError("Confirmed renewals are immutable")
        super().save(*args, **kwargs)


class LeaseContractVersion(models.Model):
    """Immutable contractual-period snapshots owned by a Lease anchor.

    This preserves the existing Lease -> Occupancy OneToOne contract while
    giving renewal a durable predecessor/successor version chain.
    """

    lease = models.ForeignKey("leasing.Lease", on_delete=models.PROTECT, related_name="contract_versions")
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="lease_contract_versions")
    version_number = models.PositiveIntegerField()
    predecessor = models.OneToOneField("self", on_delete=models.PROTECT, related_name="successor", null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notice_period_days = models.PositiveIntegerField(default=0)
    terms = models.JSONField(default=dict, blank=True)
    agreement_reference = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lease_contract_versions_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["lease_id", "version_number"]
        indexes = [
            models.Index(fields=["workspace", "lease", "version_number"], name="lease_ver_ws_lease_num_idx"),
            models.Index(fields=["workspace", "start_date"], name="lease_ver_ws_start_idx"),
            models.Index(fields=["workspace", "end_date"], name="lease_ver_ws_end_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["lease", "version_number"], name="lease_ver_lease_num_uniq"),
            models.CheckConstraint(condition=Q(version_number__gte=1), name="lease_ver_num_positive"),
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="lease_ver_end_gte_start"),
            models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_ver_rent_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_ver_dep_non_negative"),
        ]

    def clean(self):
        if self.lease_id and self.workspace_id and self.lease.workspace_id != self.workspace_id:
            raise ValidationError("Contract version must belong to the same workspace as the lease")
        if self.predecessor_id:
            if self.predecessor.lease_id != self.lease_id:
                raise ValidationError("Contract version predecessor must belong to the same lease")
            if self.predecessor.workspace_id != self.workspace_id:
                raise ValidationError("Contract version predecessor must belong to the same workspace")
            if self.version_number != self.predecessor.version_number + 1:
                raise ValidationError("Contract version must increment directly from its predecessor")
        if self.created_by_id and self.workspace_id:
            from workspaces.models import Membership
            if not Membership.objects.filter(workspace_id=self.workspace_id, user_id=self.created_by_id, is_active=True).exists():
                raise ValidationError("Contract version creator must be an active workspace member")

    def save(self, *args, **kwargs):
        self.clean()
        if self.pk:
            raise ValidationError("Lease contract versions are immutable")
        super().save(*args, **kwargs)
