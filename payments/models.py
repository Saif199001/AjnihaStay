from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q, Sum

from payments.utils import generate_invoice_number
from tenant.models import Occupancy


class Invoice(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("partial", "Partial"),
        ("paid", "Paid"),
    )

    occupancy = models.ForeignKey(
        Occupancy,
        on_delete=models.PROTECT,
        related_name="invoices"
    )

    invoice_number = models.CharField(max_length=50, unique=True)
    billing_start = models.DateField()
    billing_end = models.DateField()

    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    charges_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.billing_end < self.billing_start:
            raise ValidationError("Billing end date cannot be before start date")
        if self.rent_amount < 0:
            raise ValidationError("Rent amount cannot be negative")
        if self.charges_amount < 0:
            raise ValidationError("Charges amount cannot be negative")
        if self.paid_amount < 0:
            raise ValidationError("Paid amount cannot be negative")
        if self.total_amount is not None and self.paid_amount > self.total_amount:
            raise ValidationError("Paid amount cannot exceed invoice total")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            if (
                persisted.paid_amount != self.paid_amount
                or persisted.status != self.status
            ):
                raise ValidationError(
                    "Invoice paid amount and status are managed by the canonical financial service"
                )

            if (persisted.payments.exists() or persisted.allocations.exists()) and (
                persisted.occupancy_id != self.occupancy_id
                or persisted.rent_amount != self.rent_amount
                or persisted.charges_amount != self.charges_amount
            ):
                raise ValidationError(
                    "Invoice financial terms cannot be changed after payments exist"
                )

        if not self.invoice_number:
            self.invoice_number = generate_invoice_number()
        self.total_amount = (self.rent_amount or 0) + (self.charges_amount or 0)
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - {self.occupancy}"

    @property
    def allocated_paid_amount(self):
        """Return the canonical paid amount represented by persisted allocations."""
        return self.allocations.aggregate(total=Sum("amount"))["total"] or 0

    @property
    def due_amount(self):
        """Return the outstanding amount from canonical payment allocations."""
        return max((self.total_amount or 0) - self.allocated_paid_amount, 0)

    class Meta:
        indexes = [
            models.Index(fields=["occupancy"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(rent_amount__gte=0), name="invoice_rent_non_negative"),
            models.CheckConstraint(condition=Q(charges_amount__gte=0), name="invoice_charges_non_negative"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="invoice_paid_non_negative"),
            models.CheckConstraint(
                condition=Q(total_amount__isnull=True) | Q(total_amount__gte=0),
                name="invoice_total_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__isnull=True) | Q(paid_amount__lte=F("total_amount")),
                name="invoice_paid_lte_total",
            ),
        ]


class Payment(models.Model):

    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("bank", "Bank Transfer"),
        ("card", "Card"),
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    payment_date = models.DateField()
    reference_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")
        if not self.workspace_id:
            raise ValidationError("Workspace is required")

        if self.invoice_id:
            if self.invoice.occupancy.tenant.workspace_id != self.workspace_id:
                raise ValidationError("Payment and invoice must belong to the same workspace")

            total_paid = self.invoice.payments.exclude(id=self.id).aggregate(total=Sum("amount"))["total"] or 0
            if total_paid + self.amount > (self.invoice.total_amount or 0):
                raise ValidationError("Payment exceeds remaining amount")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            if persisted.invoice_id != self.invoice_id or persisted.amount != self.amount:
                raise ValidationError(
                    "Payment invoice and amount cannot be changed after creation"
                )
            if persisted.workspace_id != self.workspace_id:
                raise ValidationError("Payment workspace cannot be changed after creation")
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.amount} - {self.payment_method}"

    @property
    def allocated_amount(self):
        return self.allocations.aggregate(total=Sum("amount"))["total"] or 0

    @property
    def reserved_credit_amount(self):
        """Return payment principal reserved by its advance-credit record."""
        try:
            return self.advance_credit.original_amount
        except AdvanceCredit.DoesNotExist:
            return 0

    @property
    def unallocated_amount(self):
        """Return capacity not consumed by allocations or reserved advance credit."""
        return max(self.amount - self.allocated_amount - self.reserved_credit_amount, 0)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "invoice"]),
            models.Index(fields=["invoice"]),
            models.Index(fields=["payment_date"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        ]


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Allocation amount must be greater than zero")
        if self.payment.workspace_id != self.invoice.occupancy.tenant.workspace_id:
            raise ValidationError("Payment and invoice must belong to the same workspace")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            if (
                persisted.payment_id != self.payment_id
                or persisted.invoice_id != self.invoice_id
                or persisted.amount != self.amount
            ):
                raise ValidationError(
                    "Payment allocation payment, invoice and amount cannot be changed after creation"
                )
        self.clean()
        super().save(*args, **kwargs)

    @property
    def workspace_id(self):
        return self.payment.workspace_id

    class Meta:
        indexes = [
            models.Index(fields=["payment"]),
            models.Index(fields=["invoice"]),
            models.Index(fields=["invoice", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_allocation_amount_positive",
            ),
        ]


class AdvanceCredit(models.Model):
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="advance_credits",
    )
    tenant = models.ForeignKey(
        "tenant.Tenant",
        on_delete=models.PROTECT,
        related_name="advance_credits",
    )
    occupancy = models.ForeignKey(
        "tenant.Occupancy",
        on_delete=models.PROTECT,
        related_name="advance_credits",
        null=True,
        blank=True,
    )
    source_payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="advance_credit",
    )
    original_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.original_amount <= 0:
            raise ValidationError("Advance credit amount must be greater than zero")
        if self.tenant_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("Advance credit tenant must belong to the same workspace")
        if self.occupancy_id:
            if self.occupancy.tenant_id != self.tenant_id:
                raise ValidationError("Advance credit occupancy must belong to the selected tenant")
            if self.occupancy.tenant.workspace_id != self.workspace_id:
                raise ValidationError("Advance credit occupancy must belong to the same workspace")
        if self.source_payment_id and self.source_payment.workspace_id != self.workspace_id:
            raise ValidationError("Advance credit source payment must belong to the same workspace")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Advance credit {self.original_amount} - {self.tenant}"

    @property
    def applied_amount(self):
        return self.applications.aggregate(total=Sum("amount"))["total"] or 0

    @property
    def available_amount(self):
        return max(self.original_amount - self.applied_amount, 0)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "tenant"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["occupancy"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(original_amount__gt=0),
                name="advance_credit_amount_positive",
            ),
        ]


class AdvanceCreditApplication(models.Model):
    credit = models.ForeignKey(
        AdvanceCredit,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="advance_credit_applications",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Advance credit application amount must be greater than zero")
        if self.credit.workspace_id != self.invoice.occupancy.tenant.workspace_id:
            raise ValidationError("Advance credit and invoice must belong to the same workspace")
        if self.credit.tenant_id != self.invoice.occupancy.tenant_id:
            raise ValidationError("Advance credit and invoice must belong to the same tenant")

    def save(self, *args, **kwargs):
        if self.pk:
            persisted = type(self).objects.get(pk=self.pk)
            if (
                persisted.credit_id != self.credit_id
                or persisted.invoice_id != self.invoice_id
                or persisted.amount != self.amount
            ):
                raise ValidationError(
                    "Advance credit application credit, invoice and amount cannot be changed after creation"
                )
        self.clean()
        super().save(*args, **kwargs)

    @property
    def workspace_id(self):
        return self.credit.workspace_id

    class Meta:
        indexes = [
            models.Index(fields=["credit"]),
            models.Index(fields=["invoice"]),
            models.Index(fields=["invoice", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="advance_credit_application_amount_positive",
            ),
        ]
