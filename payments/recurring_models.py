from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class BillingSchedule(models.Model):
    """Durable recurring-billing configuration for an occupancy.

    This model defines *when* recurring billing becomes due. It does not itself
    create charges, invoices, or payments. Execution belongs to the future
    canonical billing service/runner.
    """

    FREQUENCY_CHOICES = (
        ("daily", "Daily"),
        ("monthly", "Monthly"),
    )

    occupancy = models.ForeignKey(
        "tenant.Occupancy",
        on_delete=models.PROTECT,
        related_name="billing_schedules",
    )
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    next_run_date = models.DateField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Billing schedule amount must be greater than zero")
        if self.next_run_date < self.occupancy.check_in_date:
            raise ValidationError("Next run date cannot be before occupancy check-in date")

        if self.occupancy_id and not self.occupancy.is_active and self.active:
            raise ValidationError("Inactive occupancy cannot have an active billing schedule")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.occupancy} - {self.frequency} - {self.next_run_date}"

    class Meta:
        indexes = [
            models.Index(fields=["active", "next_run_date"]),
            models.Index(fields=["occupancy"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="billing_schedule_amount_positive",
            ),
        ]
