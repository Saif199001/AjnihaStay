from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from tenant.charge_service import create_charge
from tenant.models import Charge

from .authorization import require_mutation_permission
from .billing_models import BillingSchedule


def _charge_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Invalid charge date")


def _next_run_date(current_date, frequency, anchor_day=None):
    if frequency == "daily":
        return date.fromordinal(current_date.toordinal() + 1)
    if frequency == "monthly":
        year = current_date.year + (1 if current_date.month == 12 else 0)
        month = 1 if current_date.month == 12 else current_date.month + 1
        day = min(anchor_day or current_date.day, monthrange(year, month)[1])
        return date(year, month, day)
    raise ValidationError("Unsupported billing frequency")


def generate_charge_from_schedule(
    user,
    workspace,
    schedule,
    charge_date=None,
    *,
    post_ledger=True,
):
    """Generate one idempotent recurring charge and advance its schedule atomically.

    The canonical recurring invoice orchestrator can suppress the charge-level
    ledger append until the invoice exists, allowing that immutable event to
    retain its canonical invoice relationship. Direct callers retain the
    historical default of posting the charge ledger event immediately.
    """
    require_mutation_permission(user, workspace)
    if charge_date is None:
        raise ValidationError("Charge date is required")
    charge_date = _charge_date(charge_date)

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
            ).get(id=schedule_id, occupancy__tenant__workspace=workspace)
        except BillingSchedule.DoesNotExist:
            raise ValidationError("Billing schedule not found")

        existing = Charge.objects.filter(
            billing_schedule=schedule,
            charge_date=charge_date,
        ).first()
        if existing:
            return existing

        if not schedule.active:
            raise ValidationError("Inactive billing schedule cannot generate a charge")

        occupancy = schedule.occupancy
        if not occupancy.is_active:
            schedule.active = False
            schedule.save(update_fields=["active", "updated_at"])
            raise ValidationError("Inactive occupancy cannot generate a charge")
        if charge_date < occupancy.check_in_date:
            raise ValidationError("Charge date cannot be before occupancy check-in date")
        if occupancy.check_out_date and charge_date >= occupancy.check_out_date:
            schedule.active = False
            schedule.save(update_fields=["active", "updated_at"])
            raise ValidationError("Charge date cannot be on or after occupancy check-out date")
        if charge_date != schedule.next_run_date:
            raise ValidationError("Charge date must match the billing schedule next run date")

        charge = create_charge(
            user,
            workspace,
            occupancy=occupancy,
            charge_type="custom",
            description=f"Recurring billing schedule #{schedule.id} ({schedule.frequency})",
            amount=schedule.amount,
            charge_date=charge_date,
            update_invoice=False,
            billing_schedule=schedule,
            post_ledger=post_ledger,
        )

        schedule.next_run_date = _next_run_date(
            schedule.next_run_date,
            schedule.frequency,
            schedule.anchor_day,
        )
        if occupancy.check_out_date and schedule.next_run_date >= occupancy.check_out_date:
            schedule.active = False
        schedule.save(update_fields=["next_run_date", "active", "updated_at"])
        return charge
