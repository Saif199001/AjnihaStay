from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class BillingSchedule(models.Model):
    """Durable recurring-billing configuration for an occupancy."""

    FREQUENCY_CHOICES = (("daily", "Daily"), ("monthly", "Monthly"))

    occupancy = models.ForeignKey(
        "tenant.Occupancy",
        on_delete=models.PROTECT,
        related_name="billing_schedules",
    )
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    next_run_date = models.DateField()
    anchor_day = models.PositiveSmallIntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Billing schedule amount must be greater than zero")
        if self.frequency == "monthly":
            if self.anchor_day is None:
                self.anchor_day = self.next_run_date.day
            if not 1 <= self.anchor_day <= 31:
                raise ValidationError("Monthly anchor day must be between 1 and 31")
        elif self.anchor_day is not None:
            raise ValidationError("Daily billing schedules cannot have a monthly anchor day")
        if self.next_run_date < self.occupancy.check_in_date:
            raise ValidationError("Next run date cannot be before occupancy check-in date")
        if self.occupancy_id and self.occupancy.check_out_date and self.next_run_date >= self.occupancy.check_out_date:
            self.active = False
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
            models.CheckConstraint(
                condition=Q(anchor_day__isnull=True) | Q(anchor_day__gte=1, anchor_day__lte=31),
                name="billing_schedule_anchor_day_valid",
            ),
            models.UniqueConstraint(
                fields=["occupancy"],
                condition=Q(active=True),
                name="billing_schedule_one_active_per_occupancy",
            ),
        ]
