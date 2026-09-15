from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from .authorization import require_mutation_permission
from .services import calculate_final_settlement
from tenant.models import Occupancy


class FinalSettlement(models.Model):
    OUTCOME_NO_DEPOSIT = "no_deposit"
    OUTCOME_FULL_REFUND = "full_refund"
    OUTCOME_PARTIAL_REFUND = "partial_refund"
    OUTCOME_FULL_RETENTION = "full_retention"

    OUTCOME_CHOICES = (
        (OUTCOME_NO_DEPOSIT, "No deposit"),
        (OUTCOME_FULL_REFUND, "Full refund"),
        (OUTCOME_PARTIAL_REFUND, "Partial refund"),
        (OUTCOME_FULL_RETENTION, "Full retention"),
    )

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="final_settlements")
    occupancy = models.OneToOneField(Occupancy, on_delete=models.PROTECT, related_name="final_settlement")
    total_rent = models.DecimalField(max_digits=10, decimal_places=2)
    total_charges = models.DecimalField(max_digits=10, decimal_places=2)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2)
    total_due = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    retained_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    refundable_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    final_balance = models.DecimalField(max_digits=10, decimal_places=2)
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES)
    settled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="final_settlements_created")
    settled_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.workspace_id and self.occupancy_id and self.occupancy.tenant.workspace_id != self.workspace_id:
            raise ValidationError("Settlement and occupancy must belong to the same workspace")
        for field in ("total_rent", "total_charges", "total_paid", "total_due", "security_deposit", "retained_deposit", "refundable_deposit"):
            if getattr(self, field) < 0:
                raise ValidationError(f"{field} cannot be negative")
        if self.retained_deposit + self.refundable_deposit != self.security_deposit:
            raise ValidationError("Deposit allocation must equal security deposit")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            snapshot_fields = (
                "workspace_id", "occupancy_id", "total_rent", "total_charges", "total_paid",
                "total_due", "security_deposit", "retained_deposit", "refundable_deposit",
                "final_balance", "outcome", "settled_by_id", "settled_at",
            )
            if any(getattr(persisted, field) != getattr(self, field) for field in snapshot_fields):
                raise ValidationError("Final settlement facts cannot be changed after settlement")
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "settled_at"], name="payments_fs_workspa_6c0f9d_idx"),
            models.Index(fields=["workspace", "outcome"], name="payments_fs_workspa_8b7a22_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(total_rent__gte=0), name="final_settlement_rent_non_negative"),
            models.CheckConstraint(condition=Q(total_charges__gte=0), name="final_settlement_charges_non_negative"),
            models.CheckConstraint(condition=Q(total_paid__gte=0), name="final_settlement_paid_non_negative"),
            models.CheckConstraint(condition=Q(total_due__gte=0), name="final_settlement_due_non_negative"),
            models.CheckConstraint(condition=Q(security_deposit__gte=0), name="final_settlement_deposit_non_negative"),
            models.CheckConstraint(condition=Q(retained_deposit__gte=0), name="final_settlement_retained_non_negative"),
            models.CheckConstraint(condition=Q(refundable_deposit__gte=0), name="final_settlement_refundable_non_negative"),
        ]


def finalize_final_settlement(user, workspace, occupancy_id, refundable_deposit=None):
    require_mutation_permission(user, workspace)

    with transaction.atomic():
        occupancy = (
            Occupancy.objects.select_for_update()
            .select_related("tenant", "unit")
            .filter(id=occupancy_id, tenant__workspace=workspace)
            .first()
        )
        if occupancy is None:
            raise ValidationError("Occupancy not found")
        existing = FinalSettlement.objects.filter(occupancy=occupancy, workspace=workspace).first()
        if existing:
            return existing
        if occupancy.check_out_date is None:
            raise ValidationError("Occupancy must have a check-out date before final settlement")

        position = calculate_final_settlement(occupancy.id, workspace)
        if position["total_due"] > Decimal("0"):
            raise ValidationError("Final settlement requires all outstanding invoices to be settled")
        deposit = position["security_deposit"]
        if refundable_deposit is None:
            refundable = deposit
        else:
            try:
                refundable = Decimal(refundable_deposit)
            except (TypeError, ValueError, InvalidOperation):
                raise ValidationError("Invalid refundable deposit amount")
        if refundable < 0 or refundable > deposit:
            raise ValidationError("Refundable deposit must be between zero and the security deposit")

        refundable = refundable.quantize(Decimal("0.01"))
        retained = deposit - refundable
        if deposit == 0:
            outcome = FinalSettlement.OUTCOME_NO_DEPOSIT
        elif refundable == deposit:
            outcome = FinalSettlement.OUTCOME_FULL_REFUND
        elif refundable == 0:
            outcome = FinalSettlement.OUTCOME_FULL_RETENTION
        else:
            outcome = FinalSettlement.OUTCOME_PARTIAL_REFUND

        settlement = FinalSettlement.objects.create(
            workspace=workspace,
            occupancy=occupancy,
            total_rent=position["total_rent"],
            total_charges=position["total_charges"],
            total_paid=position["total_paid"],
            total_due=position["total_due"],
            security_deposit=deposit,
            retained_deposit=retained,
            refundable_deposit=refundable,
            final_balance=position["final_balance"],
            outcome=outcome,
            settled_by=user,
        )

        from .ledger_service import post_ledger_event
        post_ledger_event(
            user,
            workspace,
            event_type="final_settlement_finalized",
            event_key=f"final-settlement:{settlement.pk}:finalized",
            occurred_at=settlement.settled_at,
            amount=settlement.final_balance if settlement.final_balance > 0 else None,
            occupancy=occupancy,
            metadata={
                "final_settlement_id": settlement.pk,
                "outcome": settlement.outcome,
                "security_deposit": str(settlement.security_deposit),
                "retained_deposit": str(settlement.retained_deposit),
                "refundable_deposit": str(settlement.refundable_deposit),
            },
        )
        return settlement
