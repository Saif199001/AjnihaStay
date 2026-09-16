from calendar import monthrange
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from tenant.charge_service import _create_charge_record

from .authorization import require_mutation_permission
from .billing_models import BillingSchedule
from .models import Invoice


def _parse_date(value, field_name):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name}")


def _next_run_date(current_date, frequency):
    if frequency == "daily":
        return current_date + timedelta(days=1)
    if frequency == "monthly":
        year = current_date.year + (1 if current_date.month == 12 else 0)
        month = 1 if current_date.month == 12 else current_date.month + 1
        day = min(current_date.day, monthrange(year, month)[1])
        return date(year, month, day)
    raise ValidationError("Unsupported billing frequency")


def _get_locked_schedule(schedule, workspace):
    try:
        schedule_id = int(getattr(schedule, "id", schedule))
    except (TypeError, ValueError):
        raise ValidationError("Billing schedule not found")
    if schedule_id <= 0:
        raise ValidationError("Billing schedule not found")

    try:
        return BillingSchedule.objects.select_for_update().select_related(
            "occupancy__tenant"
        ).get(
            id=schedule_id,
            occupancy__tenant__workspace=workspace,
        )
    except BillingSchedule.DoesNotExist:
        raise ValidationError("Billing schedule not found")


def _validate_schedule_run(schedule, run_date, *, action):
    if not schedule.active:
        if action == "billing":
            raise ValidationError("Inactive billing schedule cannot generate an invoice")
        raise ValidationError(f"Inactive billing schedule cannot generate a {action}")

    occupancy = schedule.occupancy
    if not occupancy.is_active:
        if action == "billing":
            raise ValidationError("Inactive occupancy cannot generate an invoice")
        raise ValidationError(f"Inactive occupancy cannot generate a {action}")
    if run_date < occupancy.check_in_date:
        if action == "billing":
            raise ValidationError("Billing date cannot be before occupancy check-in date")
        raise ValidationError(f"{action.capitalize()} date cannot be before occupancy check-in date")
    if occupancy.check_out_date and run_date > occupancy.check_out_date:
        if action == "billing":
            raise ValidationError("Billing date cannot be after occupancy check-out date")
        raise ValidationError(f"{action.capitalize()} date cannot be after occupancy check-out date")
    if run_date != schedule.next_run_date:
        if action == "billing":
            raise ValidationError("Billing date must match the billing schedule next run date")
        raise ValidationError(f"{action.capitalize()} date must match the billing schedule next run date")
    return occupancy


def _advance_schedule(schedule):
    schedule.next_run_date = _next_run_date(schedule.next_run_date, schedule.frequency)
    if schedule.occupancy.check_out_date and schedule.next_run_date > schedule.occupancy.check_out_date:
        schedule.active = False
    schedule.save(update_fields=["next_run_date", "active", "updated_at"])


def _post_charge_ledger(user, workspace, charge, *, invoice=None):
    from .ledger_service import post_ledger_event

    return post_ledger_event(
        user,
        workspace,
        event_type="charge_generated",
        event_key=f"charge:{charge.pk}:generated",
        occurred_at=charge.created_at,
        amount=charge.amount,
        invoice=invoice,
        occupancy=charge.occupancy,
        metadata={
            "charge_id": charge.pk,
            "charge_type": charge.charge_type,
            "recurring": True,
        },
    )


def generate_recurring_charge(
    user,
    workspace,
    schedule,
    charge_date=None,
    *,
    post_ledger=True,
):
    """Canonical recurring-charge orchestration; owns schedule cursor advancement."""
    require_mutation_permission(user, workspace)
    if charge_date is None:
        raise ValidationError("Charge date is required")
    charge_date = _parse_date(charge_date, "charge date")

    with transaction.atomic():
        schedule = _get_locked_schedule(schedule, workspace)
        existing = schedule.charges.filter(charge_date=charge_date).first()
        if existing:
            if post_ledger:
                _post_charge_ledger(user, workspace, existing)
            return existing
        occupancy = _validate_schedule_run(schedule, charge_date, action="charge")
        charge = _create_charge_record(
            user,
            workspace,
            occupancy=occupancy,
            charge_type="custom",
            description=f"Recurring billing schedule #{schedule.id} ({schedule.frequency})",
            amount=schedule.amount,
            charge_date=charge_date,
            update_invoice=False,
            billing_schedule=schedule,
            post_ledger=False,
        )
        _advance_schedule(schedule)
        if post_ledger:
            _post_charge_ledger(user, workspace, charge)
        return charge


def generate_recurring_invoice(user, workspace, schedule, billing_date=None, due_date=None):
    """Canonical recurring-invoice orchestration; creates invoice + charge atomically."""
    require_mutation_permission(user, workspace)
    if billing_date is None:
        raise ValidationError("Billing date is required")
    billing_date = _parse_date(billing_date, "billing date")
    due_date = _parse_date(due_date, "due date") if due_date is not None else None

    with transaction.atomic():
        schedule = _get_locked_schedule(schedule, workspace)
        occupancy = schedule.occupancy
        existing_invoice = Invoice.objects.filter(occupancy=occupancy, billing_start=billing_date).first()
        if existing_invoice:
            return existing_invoice

        occupancy = _validate_schedule_run(schedule, billing_date, action="billing")
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
        charge = _create_charge_record(
            user,
            workspace,
            occupancy=occupancy,
            charge_type="custom",
            description=f"Recurring billing schedule #{schedule.id} ({schedule.frequency})",
            amount=schedule.amount,
            charge_date=billing_date,
            update_invoice=True,
            invoice=invoice,
            billing_schedule=schedule,
            post_ledger=False,
        )
        _post_charge_ledger(user, workspace, charge, invoice=invoice)
        _advance_schedule(schedule)
        invoice.refresh_from_db()

        from .ledger_service import post_ledger_event
        post_ledger_event(
            user,
            workspace,
            event_type="recurring_invoice_generated",
            event_key=f"recurring-invoice:{invoice.pk}:generated",
            occurred_at=invoice.created_at,
            amount=invoice.total_amount,
            invoice=invoice,
            occupancy=occupancy,
            metadata={"billing_schedule_id": schedule.pk, "billing_date": str(billing_date)},
        )
        return invoice
