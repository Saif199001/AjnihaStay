from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class PaymentRefund(models.Model):
    STATUS_REQUESTED = "requested"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_REQUESTED, "Requested"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="payment_refunds",
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    reason = models.TextField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    idempotency_key = models.CharField(max_length=100, blank=True, null=True)
    failure_reason = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_refunds_requested",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Refund amount must be greater than zero")
        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError("Invalid refund status")
        if not self.reason or not self.reason.strip():
            raise ValidationError("Refund reason is required")
        if self.status == self.STATUS_FAILED and not self.failure_reason.strip():
            raise ValidationError("Refund failure reason is required")
        if self.status != self.STATUS_FAILED and self.failure_reason.strip():
            raise ValidationError("Failure reason is only valid for failed refunds")
        if not self.workspace_id:
            raise ValidationError("Workspace is required")
        if self.payment_id and self.payment.workspace_id != self.workspace_id:
            raise ValidationError("Refund and payment must belong to the same workspace")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            if (
                persisted.workspace_id != self.workspace_id
                or persisted.payment_id != self.payment_id
                or persisted.amount != self.amount
                or persisted.reason != self.reason
                or persisted.reference != self.reference
                or persisted.idempotency_key != self.idempotency_key
                or persisted.requested_by_id != self.requested_by_id
            ):
                raise ValidationError("Payment refunds cannot change financial facts after creation")
            if persisted.status != self.status:
                allowed = {
                    self.STATUS_REQUESTED: {self.STATUS_PROCESSING, self.STATUS_FAILED},
                    self.STATUS_PROCESSING: {self.STATUS_SUCCEEDED, self.STATUS_FAILED},
                    self.STATUS_SUCCEEDED: set(),
                    self.STATUS_FAILED: set(),
                }
                if self.status not in allowed.get(persisted.status, set()):
                    raise ValidationError("Invalid refund state transition")
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Refund {self.amount} - {self.payment}"

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "payment"], name="payments_pr_workspa_pay_idx"),
            models.Index(fields=["payment", "status"], name="payments_pr_payment_status_idx"),
            models.Index(fields=["workspace", "status", "created_at"], name="payments_pr_workspa_stat_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_refund_amount_positive"),
            models.CheckConstraint(condition=~Q(reason=""), name="payment_refund_reason_non_empty"),
            models.CheckConstraint(condition=Q(status__in=["requested", "processing", "succeeded", "failed"]), name="payment_refund_status_valid"),
            models.UniqueConstraint(fields=["workspace", "idempotency_key"], name="payment_refund_workspace_idempotency_key_uniq"),
        ]
