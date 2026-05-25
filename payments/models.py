from django.db import models
from tenant.models import Occupancy
from payments.utils import generate_invoice_number
from django.core.exceptions import ValidationError
from django.db.models import Sum


class Invoice(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("partial", "Partial"),
        ("paid", "Paid"),
    )

    occupancy = models.ForeignKey(
        Occupancy,
        on_delete=models.CASCADE,
        related_name="invoices"
    )

    invoice_number = models.CharField(
        max_length=50,
        unique=True
    )

    billing_start = models.DateField()
    billing_end = models.DateField()

    rent_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    charges_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True, blank=True   # 🔥 FIX (safe calculation)
    )

    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    due_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.billing_end < self.billing_start:
            raise ValidationError("Billing end date cannot be before start date")

    def save(self, *args, **kwargs):
        self.clean()

        # 🔥 Invoice number generate once
        if not self.invoice_number:
            self.invoice_number = generate_invoice_number()

        # 🔥 Safe total calculation
        
        self.total_amount = ((self.rent_amount or 0) + (self.charges_amount or 0))

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - {self.occupancy}"

    # 🔥 AUTO DUE CALCULATION
    @property
    def due_amount(self):
        return max(self.total_amount - self.paid_amount, 0)

    class Meta:
        indexes = [
            models.Index(fields=["occupancy"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]


class Payment(models.Model):

    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("bank", "Bank Transfer"),
        ("card", "Card"),
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS
    )

    payment_date = models.DateField()

    reference_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):

        if self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")

        # 🔥 Exclude current payment (important for update case)
        total_paid = self.invoice.payments.exclude(id=self.id).aggregate(
            total=Sum("amount")
        )["total"] or 0

        if total_paid + self.amount > self.invoice.total_amount:
            raise ValidationError("Payment exceeds remaining amount")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.amount} - {self.payment_method}"

    class Meta:
        indexes = [
            models.Index(fields=["invoice"]),
            models.Index(fields=["payment_date"]),
        ]