from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from .authorization import require_mutation_permission
from .billing_models import BillingSchedule
from .charge_generation_service import _next_run_date, generate_charge_from_schedule
from .invoice_generation_service import generate_invoice_for_occupancy


DEFAULT_MAX_CATCH_UP = 12
MAX_CATCH_UP = 100


def generate_recurring_billing_occurrence(user, workspace, schedule, occurrence_date=None):
    """Atomically generate the charge and invoice for one recurring occurrence."""
    require_mutation_permission(user, workspace)
    with transaction.atomic():
        schedule_id = getattr(schedule, "id", schedule)
        try:
            schedule_id = int(schedule_id)
        except (TypeError, ValueError):
            raise ValidationError("Billing schedule not found")

        locked = BillingSchedule.objects.select_for_update().select_related("occupancy__tenant").get(
            id=schedule_id, occupancy__tenant__workspace=workspace
        )

        start = occurrence_date or locked.next_run_date
        if isinstance(start, str):
            try:
                start = date.fromisoformat(start)
            except ValueError:
                raise ValidationError("Invalid occurrence date")

        period_end = _next_run_date(start, locked.frequency, locked.anchor_day)
        if locked.occupancy.check_out_date:
            period_end = min(period_end, locked.occupancy.check_out_date)

        charge = generate_charge_from_schedule(user, workspace, locked, charge_date=start)
        if period_end <= start:
            raise ValidationError("Recurring billing period has no valid end date")

        invoice, created = generate_invoice_for_occupancy(
            user,
            workspace,
            locked.occupancy,
            billing_start=start,
            billing_end=period_end,
            due_date=start,
            ledger_event_type="recurring_invoice_generated",
            ledger_event_key=f"recurring-invoice:{locked.pk}:{start.isoformat()}",
            ledger_metadata={
                "billing_schedule_id": locked.pk,
                "billing_date": str(start),
                "charge_id": charge.pk,
            },
        )
        return {
            "charge": charge,
            "invoice": invoice,
            "invoice_created": created,
            "billing_start": start,
            "billing_end": period_end,
        }


def generate_due_recurring_billing(user, workspace, schedule, as_of_date=None, catch_up=True, max_occurrences=DEFAULT_MAX_CATCH_UP):
    """Process due recurring occurrences with explicit bounded catch-up."""
    require_mutation_permission(user, workspace)
    as_of_date = as_of_date or date.today()
    if isinstance(as_of_date, str):
        try:
            as_of_date = date.fromisoformat(as_of_date)
        except ValueError:
            raise ValidationError("Invalid as-of date")

    try:
        max_occurrences = int(max_occurrences)
    except (TypeError, ValueError):
        raise ValidationError("Invalid max occurrences")
    if not 1 <= max_occurrences <= MAX_CATCH_UP:
        raise ValidationError(f"max_occurrences must be between 1 and {MAX_CATCH_UP}")

    results = []
    for _ in range(max_occurrences):
        schedule_row = BillingSchedule.objects.filter(
            id=getattr(schedule, "id", schedule),
            occupancy__tenant__workspace=workspace,
            active=True,
        ).select_related("occupancy").first()
        if not schedule_row or schedule_row.next_run_date > as_of_date:
            break
        results.append(generate_recurring_billing_occurrence(user, workspace, schedule_row))
        if not catch_up:
            break
    return results
