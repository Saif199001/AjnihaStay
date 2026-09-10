from calendar import monthrange
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from tenant.charge_service import create_charge

from .authorization import require_mutation_permission
from .billing_models import BillingSchedule
from .models import Invoice


def _invoice_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Invalid billing date")


def _next_run_date(current_date, frequency):
    if frequency == "daily":
        return current_date + timedelta(days=1)
    if frequency == "monthly":
        year = current_date.year + (1 if current_date.month == 12 else 0)
        month = 1 if current_date.month == 12 else current_date.month + 1
        day = min(current_date.day, monthrange(year, month)[1])
        return date(year, month, day)
    raise ValidationError("Unsupported billing frequency")


def generate_invoice_from_schedule(user, workspace, schedule, billing_date=None, due_date=None):
    """Atomically create the next recurring invoice and its charge for a schedule."""
    require_mutation_permission(user, workspace)
    if billing_date is None:
        raise ValidationError("Billing date is required")
    billing_date = _invoice_date(billing_date)
    if due_date is not None:
        due_date = _invoice_date(due_date)

    with transaction.atomic():
        try:
            schedule_id = int(getattr(schedule, "id", schedule))
        except (TypeError, ValueError):
            raise ValidationError("Billing schedule not found")
        if schedule_id <= 0:
            raise ValidationError("Billing schedule not found")

        try:
            schedule = BillingSchedule.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(
                id=schedule_id,
                occupancy__tenant__workspace=workspace,
            )
        except BillingSchedule.DoesNotExist:
            raise ValidationError("Billing schedule not found")

        if not schedule.active:
            raise ValidationError("Inactive billing schedule cannot generate an invoice")

        occupancy = schedule.occupancy
        if not occupancy.is_active:
            raise ValidationError("Inactive occupancy cannot generate an invoice")
        if billing_date < occupancy.check_in_date:
            raise ValidationError("Billing date cannot be before occupancy check-in date")
        if occupancy.check_out_date and billing_date > occupancy.check_out_date:
            raise ValidationError("Billing date cannot be after occupancy check-out date")
        if billing_date != schedule.next_run_date:
            raise ValidationError("Billing date must match the billing schedule next run date")

        next_run_date = _next_run_date(schedule.next_run_date, schedule.frequency)
        billing_end = next_run_date - timedelta(days=1)
        if occupancy.check_out_date:
            billing_end = min(billing_end, occupancy.check_out_date)
        if billing_end < billing_date:
            raise ValidationError("Recurring billing period has no active occupancy days")

        invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=billing_date,
            billing_end=billing_end,
            rent_amount=0,
            charges_amount=0,
            due_date=due_date or billing_end,
        )

        create_charge(
            user,
            workspace,
            occupancy=occupancy,
            charge_type="custom",
            description=f"Recurring billing schedule #{schedule.id} ({schedule.frequency})",
            amount=schedule.amount,
            charge_date=billing_date,
            update_invoice=True,
            invoice=invoice,
        )

        schedule.next_run_date = next_run_date
        schedule.save(update_fields=["next_run_date", "updated_at"])
        invoice.refresh_from_db()
        return invoice
