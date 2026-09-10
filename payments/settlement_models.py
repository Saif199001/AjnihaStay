from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class OccupancySettlement(models.Model):
    OUTCOME_NO_DEPOSIT = "no_deposit"
    OUTCOME_FULL_REFUND = "full_refund"
    OUTCOME_PARTIAL_REFUND = "partial_refund"
    OUTCOME_FULL_RETENTION = "full_retention"
    OUTCOMES = (
        (OUTCOME_NO_DEPOSIT, "No deposit"),
        (OUTCOME_FULL_REFUND, "Full refund"),
        (OUTCOME_PARTIAL_REFUND, "Partial refund"),
        (OUTCOME_FULL_RETENTION, "Full retention"),
    )

    STATE_SETTLED = "settled"

    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, related_name="occupancy_settlements"
    )
    occupancy = models.OneToOneField(
        "tenant.Occupancy", on_delete=models.PROTECT, related_name="settlement"
    )
    state = models.CharField(max_length=20, default=STATE_SETTLED)
    outcome = models.CharField(max_length=30, choices=OUTCOMES)
    invoice_outstanding = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    refundable_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    retained_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="occupancy_settlements_created"
    )
    settled_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.state != self.STATE_SETTLED:
            raise ValidationError("Invalid settlement state")
        if self.invoice_outstanding != Decimal("0.00"):
            raise ValidationError("Settlement cannot have outstanding invoice balance")
        if self.security_deposit < 0 or self.refundable_deposit < 0 or self.retained_deposit < 0:
            raise ValidationError("Settlement deposit amounts cannot be negative")
        if self.refundable_deposit + self.retained_deposit != self.security_deposit:
            raise ValidationError("Refundable and retained deposit must equal security deposit")
        if self.outcome == self.OUTCOME_NO_DEPOSIT and self.security_deposit != 0:
            raise ValidationError("No-deposit settlement must have zero security deposit")
        if self.outcome == self.OUTCOME_FULL_REFUND and self.refundable_deposit != self.security_deposit:
            raise ValidationError("Full-refund settlement must refund the full deposit")
        if self.outcome == self.OUTCOME_FULL_RETENTION and self.retained_deposit != self.security_deposit:
            raise ValidationError("Full-retention settlement must retain the full deposit")
        if self.outcome == self.OUTCOME_PARTIAL_REFUND:
            if not (Decimal("0.00") < self.refundable_deposit < self.security_deposit):
                raise ValidationError("Partial-refund settlement must refund part of the deposit")

        if self.workspace_id != self.occupancy.tenant.workspace_id:
            raise ValidationError("Settlement and occupancy must belong to the same workspace")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            fields = (
                "workspace_id", "occupancy_id", "state", "outcome", "invoice_outstanding",
                "security_deposit", "refundable_deposit", "retained_deposit", "settled_by_id",
            )
            if any(getattr(persisted, field) != getattr(self, field) for field in fields):
                raise ValidationError("Settlement financial facts cannot be changed after creation")
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "settled_at"]),
            models.Index(fields=["occupancy"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(invoice_outstanding=0), name="settlement_outstanding_zero"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="settlement_deposit_non_negative"),
            models.CheckConstraint(condition=Q(refundable_deposit__gte=0), name="settlement_refundable_non_negative"),
            models.CheckConstraint(condition=Q(retained_deposit__gte=0), name="settlement_retained_non_negative"),
            models.CheckConstraint(
                condition=Q(refundable_deposit__gte=0) & Q(retained_deposit__gte=0),
                name="settlement_deposit_parts_non_negative",
            ),
        ]
