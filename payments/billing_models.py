from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import Q

_BILLING_SCHEDULE_MUTATION_ALLOWED = ContextVar("billing_schedule_mutation_allowed", default=False)


@contextmanager
def _allow_billing_schedule_mutation():
    token = _BILLING_SCHEDULE_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _BILLING_SCHEDULE_MUTATION_ALLOWED.reset(token)


class BillingScheduleQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        raise PermissionDenied("Billing schedules must be changed through the canonical billing service.")

    def update(self, **kwargs):
        raise PermissionDenied("Billing schedules must be changed through the canonical billing service.")

    def bulk_update(self, objs, fields, *args, **kwargs):
        raise PermissionDenied("Billing schedules must be changed through the canonical billing service.")

    def delete(self):
        raise PermissionDenied("Billing schedules cannot be deleted directly.")


class BillingSchedule(models.Model):
    """Durable recurring-billing configuration for an occupancy."""

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

    objects = BillingScheduleQuerySet.as_manager()

    def clean(self):
        allowed_frequencies = {value for value, _label in self.FREQUENCY_CHOICES}
        if self.frequency not in allowed_frequencies:
            raise ValidationError("Invalid billing schedule frequency")
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Billing schedule amount must be greater than zero")
        if self.next_run_date < self.occupancy.check_in_date:
            raise ValidationError("Next run date cannot be before occupancy check-in date")
        if self.occupancy_id and not self.occupancy.is_active and self.active:
            raise ValidationError("Inactive occupancy cannot have an active billing schedule")

    def save(self, *args, **kwargs):
        if not _BILLING_SCHEDULE_MUTATION_ALLOWED.get():
            raise PermissionDenied("Billing schedules must be changed through the canonical billing service.")
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Billing schedules cannot be deleted directly.")

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
