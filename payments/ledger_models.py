from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class FinancialLedgerEntry(models.Model):
    """Immutable append-only financial event record.

    This is a financial subledger/history layer, not an accounting GL. Domain
    services remain the source of financial truth; ledger entries record the
    committed financial event for audit, reporting, and future reconciliation.
    """

    EVENT_TYPES = (
        ("invoice_created", "Invoice created"),
        ("payment_recorded", "Payment recorded"),
        ("payment_allocated", "Payment allocated"),
        ("advance_credit_created", "Advance credit created"),
        ("advance_credit_applied", "Advance credit applied"),
        ("adjustment_created", "Adjustment created"),
        ("charge_generated", "Charge generated"),
        ("recurring_invoice_generated", "Recurring invoice generated"),
        ("late_fee_generated", "Late fee generated"),
        ("final_settlement_finalized", "Final settlement finalized"),
        ("refund_requested", "Refund requested"),
        ("refund_processing", "Refund processing"),
        ("refund_succeeded", "Refund succeeded"),
        ("refund_failed", "Refund failed"),
    )

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="financial_ledger_entries")
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    event_key = models.CharField(max_length=160)
    occurred_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    invoice = models.ForeignKey("payments.Invoice", on_delete=models.PROTECT, related_name="financial_ledger_entries", null=True, blank=True)
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, related_name="financial_ledger_entries", null=True, blank=True)
    occupancy = models.ForeignKey("tenant.Occupancy", on_delete=models.PROTECT, related_name="financial_ledger_entries", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="financial_ledger_entries_created", null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Ledger amount must be greater than zero")
        if len((self.currency or "").strip()) != 3:
            raise ValidationError("Ledger currency must be a 3-letter code")
        if not self.workspace_id:
            raise ValidationError("Workspace is required")
        related_workspace_ids = []
        if self.invoice_id:
            related_workspace_ids.append(self.invoice.occupancy.tenant.workspace_id)
        if self.payment_id:
            related_workspace_ids.append(self.payment.workspace_id)
        if self.occupancy_id:
            related_workspace_ids.append(self.occupancy.tenant.workspace_id)
        if any(value != self.workspace_id for value in related_workspace_ids):
            raise ValidationError("Ledger references must belong to the same workspace")
        if self.invoice_id and self.occupancy_id and self.invoice.occupancy_id != self.occupancy_id:
            raise ValidationError("Ledger invoice and occupancy must match")
        if self.payment_id and self.invoice_id and self.payment.invoice_id and self.payment.invoice_id != self.invoice_id:
            raise ValidationError("Ledger payment and invoice must match")
        if self.payment_id and self.occupancy_id and self.payment.invoice_id:
            if self.payment.invoice.occupancy_id != self.occupancy_id:
                raise ValidationError("Ledger payment and occupancy must match")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "workspace_id", "event_type", "event_key", "occurred_at", "amount",
                "currency", "invoice_id", "payment_id", "occupancy_id", "created_by_id",
                "metadata", "created_at",
            )
            if any(getattr(persisted, field) != getattr(self, field) for field in immutable_fields):
                raise ValidationError("Financial ledger entries cannot be changed after creation")
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "occurred_at"], name="payments_fl_workspa_4d4f8a_idx"),
            models.Index(fields=["workspace", "event_type"], name="payments_fl_evt_type_idx"),
            models.Index(fields=["invoice", "occurred_at"], name="payments_fl_invoice_8b2c17_idx"),
            models.Index(fields=["payment", "occurred_at"], name="payments_fl_payment_6f0a42_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "event_key"], name="financial_ledger_workspace_event_key_unique"),
            models.CheckConstraint(condition=Q(amount__isnull=True) | Q(amount__gt=0), name="financial_ledger_amount_positive"),
        ]
