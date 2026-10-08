from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import Q


_LATE_FEE_CREATION_ALLOWED = ContextVar("late_fee_creation_allowed", default=False)


@contextmanager
def _allow_late_fee_creation():
    token = _LATE_FEE_CREATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _LATE_FEE_CREATION_ALLOWED.reset(token)


class LateFeePolicy(models.Model):
    MODE_FIXED = "fixed"
    MODE_PERCENTAGE = "percentage"
    MODES = ((MODE_FIXED, "Fixed"), (MODE_PERCENTAGE, "Percentage"))

    workspace = models.OneToOneField("workspaces.Workspace", on_delete=models.PROTECT, related_name="late_fee_policy")
    enabled = models.BooleanField(default=False)
    grace_period_days = models.PositiveIntegerField(default=0)
    calculation_mode = models.CharField(max_length=20, choices=MODES, default=MODE_FIXED)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    minimum_overdue_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.01"))
    maximum_late_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.grace_period_days < 0: raise ValidationError("Grace period cannot be negative")
        if self.rate < 0: raise ValidationError("Late fee rate/amount cannot be negative")
        if self.minimum_overdue_balance <= 0: raise ValidationError("Minimum overdue balance must be greater than zero")
        if self.maximum_late_fee is not None and self.maximum_late_fee <= 0: raise ValidationError("Maximum late fee must be greater than zero")
        if self.calculation_mode not in dict(self.MODES): raise ValidationError("Invalid late fee calculation mode")
        if self.calculation_mode == self.MODE_PERCENTAGE and self.rate > 100: raise ValidationError("Late fee percentage cannot exceed 100")
        if self.rate != self.rate.quantize(Decimal("0.01")): raise ValidationError("Late fee rate/amount cannot have more than two decimal places")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(grace_period_days__gte=0), name="late_fee_grace_non_negative"),
            models.CheckConstraint(condition=Q(rate__gte=0), name="late_fee_rate_non_negative"),
            models.CheckConstraint(condition=Q(minimum_overdue_balance__gt=0), name="late_fee_min_balance_positive"),
        ]


class LateFeeQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        if not _LATE_FEE_CREATION_ALLOWED.get():
            raise PermissionDenied("Late fee creation must be performed through the canonical late fee service.")
        return super().bulk_create(objs, *args, **kwargs)

    def update(self, **kwargs):
        raise PermissionDenied("Late fee financial facts cannot be updated directly.")

    def bulk_update(self, objs, fields, *args, **kwargs):
        raise PermissionDenied("Late fee financial facts cannot be updated directly.")

    def delete(self):
        raise PermissionDenied("Late fees cannot be deleted.")


class LateFee(models.Model):
    objects = LateFeeQuerySet.as_manager()
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="late_fees")
    invoice = models.ForeignKey("payments.Invoice", on_delete=models.PROTECT, related_name="late_fees")
    policy = models.ForeignKey(LateFeePolicy, on_delete=models.PROTECT, related_name="late_fees")
    effective_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2)
    calculation_mode = models.CharField(max_length=20, choices=LateFeePolicy.MODES)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="late_fees_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0: raise ValidationError("Late fee amount must be greater than zero")
        if self.outstanding_balance <= 0: raise ValidationError("Late fee outstanding balance must be greater than zero")
        if self.workspace_id != self.invoice.occupancy.tenant.workspace_id: raise ValidationError("Late fee and invoice must belong to the same workspace")
        if self.policy.workspace_id != self.workspace_id: raise ValidationError("Late fee policy must belong to the same workspace")

    def save(self, *args, **kwargs):
        if not self.pk and not _LATE_FEE_CREATION_ALLOWED.get():
            raise PermissionDenied("Late fee creation must be performed through the canonical late fee service.")
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            fields = ("workspace_id", "invoice_id", "policy_id", "effective_date", "amount", "outstanding_balance", "calculation_mode", "reason", "created_by_id")
            if any(getattr(persisted, field) != getattr(self, field) for field in fields):
                raise ValidationError("Late fee financial facts cannot be changed after creation")
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Late fees cannot be deleted.")

    class Meta:
        indexes = [models.Index(fields=["workspace", "invoice"]), models.Index(fields=["invoice", "effective_date"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="late_fee_amount_positive"),
            models.CheckConstraint(condition=Q(outstanding_balance__gt=0), name="late_fee_balance_positive"),
            models.UniqueConstraint(fields=["workspace", "invoice", "policy", "effective_date"], name="late_fee_invoice_policy_date_unique"),
        ]
