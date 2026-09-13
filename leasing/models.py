from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Lease(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PENDING_SIGNATURE = "pending_signature"
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_TERMINATED = "terminated"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING_SIGNATURE, "Pending Signature"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_TERMINATED, "Terminated"),
        (STATUS_CANCELLED, "Cancelled"),
    )
    VALID_STATUSES = {choice[0] for choice in STATUS_CHOICES}

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="leases",
    )
    occupancy = models.OneToOneField(
        "tenant.Occupancy",
        on_delete=models.PROTECT,
        related_name="lease",
    )
    agreement_number = models.CharField(max_length=100, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notice_period_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    terms = models.JSONField(default=dict, blank=True)
    agreement_reference = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leases_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leases_updated",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "status"], name="lease_ws_status_idx"),
            models.Index(fields=["workspace", "start_date"], name="lease_ws_start_idx"),
            models.Index(fields=["workspace", "end_date"], name="lease_ws_end_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="lease_end_gte_start"),
            models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_rent_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_deposit_non_negative"),
            models.CheckConstraint(condition=Q(status__in=["draft", "pending_signature", "active", "expired", "terminated", "cancelled"]), name="lease_status_valid"),
        ]

    def clean(self):
        if self.status not in self.VALID_STATUSES:
            raise ValidationError("Invalid lease status")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("Lease end date cannot be before start date")
        if self.occupancy_id and self.workspace_id:
            if self.occupancy.tenant.workspace_id != self.workspace_id:
                raise ValidationError("Lease occupancy must belong to the same workspace")
        if self.created_by_id and self.workspace_id:
            from workspaces.models import Membership
            if not Membership.objects.filter(workspace_id=self.workspace_id, user_id=self.created_by_id, is_active=True).exists():
                raise ValidationError("Lease creator must be an active workspace member")

    def save(self, *args, **kwargs):
        allow_lifecycle_mutation = kwargs.pop("_allow_lifecycle_mutation", False)
        if self.pk and not allow_lifecycle_mutation:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous_status is not None and previous_status != self.status:
                raise ValidationError(
                    "Lease lifecycle status changes must use the canonical lifecycle service"
                )
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.agreement_number or f"Lease #{self.pk}"


from .lifecycle_models import LeaseLifecycleEvent, LeaseNotice  # noqa: E402,F401
