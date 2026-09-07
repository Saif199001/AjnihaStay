from django.core.exceptions import ValidationError

from tenant.models import Occupancy

from .billing_models import BillingSchedule


def _get_occupancy(occupancy_id, workspace):
    try:
        return Occupancy.objects.select_related("tenant").get(
            id=occupancy_id,
            tenant__workspace=workspace,
        )
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")


def create_billing_schedule(user, workspace, data):
    occupancy = _get_occupancy(data.get("occupancy"), workspace)
    schedule = BillingSchedule(
        occupancy=occupancy,
        frequency=data.get("frequency"),
        amount=data.get("amount"),
        next_run_date=data.get("next_run_date"),
        active=data.get("active", True),
    )
    schedule.save()
    return schedule


def get_billing_schedules(workspace):
    return BillingSchedule.objects.filter(
        occupancy__tenant__workspace=workspace,
    ).select_related("occupancy", "occupancy__tenant").order_by("next_run_date", "id")


def get_billing_schedule(schedule_id, workspace):
    try:
        return BillingSchedule.objects.select_related("occupancy", "occupancy__tenant").get(
            id=schedule_id,
            occupancy__tenant__workspace=workspace,
        )
    except BillingSchedule.DoesNotExist:
        raise ValidationError("Billing schedule not found")


def update_billing_schedule(user, workspace, schedule_id, data):
    schedule = get_billing_schedule(schedule_id, workspace)
    if "occupancy" in data:
        occupancy = _get_occupancy(data.get("occupancy"), workspace)
        schedule.occupancy = occupancy
    for field in ("frequency", "amount", "next_run_date", "active"):
        if field in data:
            setattr(schedule, field, data[field])
    schedule.save()
    return schedule
