from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from tenant.models import Charge

from .billing_models import BillingSchedule


def _charge_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Invalid charge date")


def generate_charge_from_schedule(user, workspace, schedule, charge_date=None):
    """Generate one recurring charge from a workspace-scoped billing schedule."""
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
            ).get(
                id=schedule_id,
                occupancy__tenant__workspace=workspace,
            )
        except BillingSchedule.DoesNotExist:
            raise ValidationError("Billing schedule not found")

        if not schedule.active:
            raise ValidationError("Inactive billing schedule cannot generate a charge")

        occupancy = schedule.occupancy
        if not occupancy.is_active:
            raise ValidationError("Inactive occupancy cannot generate a charge")
        if charge_date < occupancy.check_in_date:
            raise ValidationError("Charge date cannot be before occupancy check-in date")
        if occupancy.check_out_date and charge_date > occupancy.check_out_date:
            raise ValidationError("Charge date cannot be after occupancy check-out date")

        charge = Charge(
            occupancy=occupancy,
            charge_type="custom",
            description=f"Recurring billing schedule #{schedule.id} ({schedule.frequency})",
            amount=schedule.amount,
            charge_date=charge_date,
        )
        charge.save()
        return charge
