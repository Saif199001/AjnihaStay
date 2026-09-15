from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from .authorization import require_mutation_permission
from .billing_models import BillingSchedule
from .charge_generation_service import _next_run_date, generate_charge_from_schedule
from .invoice_generation_service import generate_invoice_for_occupancy
from .ledger_service import post_ledger_event


DEFAULT_MAX_CATCH_UP = 12
MAX_CATCH_UP = 100


def generate_recurring_billing_occurrence(
    user,
    workspace,
    schedule,
    occurrence_date=None,
    due_date=None,
    *,
    charge_generator=generate_charge_from_schedule,
):
    """Atomically generate one recurring charge and invoice.

    An occurrence is identified by billing schedule plus occurrence date.
    Replaying a committed occurrence returns its existing financial records.
    """
    require_mutation_permission(user, workspace)
    with transaction.atomic():
        schedule_id = getattr(schedule, "id", schedule)
        try:
            schedule_id = int(schedule_id)
        except (TypeError, ValueError):
            raise ValidationError("Billing schedule not found")
        if schedule_id <= 0:
            raise ValidationError("Billing schedule not found")

        try:
            locked = BillingSchedule.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(id=schedule_id, occupancy__tenant__workspace=workspace)
        except BillingSchedule.DoesNotExist as exc:
            raise ValidationError("Billing schedule not found") from exc

        start = occurrence_date or locked.next_run_date
        if isinstance(start, str):
            try:
                start = date.fromisoformat(start)
            except ValueError as exc:
                raise ValidationError("Invalid billing date") from exc
        if not isinstance(start, date):
            raise ValidationError("Invalid billing date")

        if due_date is not None and isinstance(due_date, str):
            try:
                due_date = date.fromisoformat(due_date)
            except ValueError as exc:
                raise ValidationError("Invalid due date") from exc

        next_run = _next_run_date(start, locked.frequency, locked.anchor_day)
        period_end = start if locked.frequency == "daily" else next_run - timedelta(days=1)
        if locked.occupancy.check_out_date:
            period_end = min(period_end, locked.occupancy.check_out_date)
        if period_end < start:
            raise ValidationError("Recurring billing period has no valid end date")
        if due_date is not None and due_date < start:
            raise ValidationError("Recurring invoice due date cannot be before billing date")

        existing_charge = locked.charges.filter(charge_date=start).first()
        existing_invoice = locked.occupancy.invoices.filter(
            billing_start=start,
            billing_end=period_end,
        ).first()

        if existing_charge and existing_invoice:
            return {
                "charge": existing_charge,
                "invoice": existing_invoice,
                "invoice_created": False,
                "billing_start": start,
                "billing_end": period_end,
            }

        if existing_charge:
            charge = existing_charge
        else:
            if not locked.active:
                raise ValidationError("Inactive billing schedule cannot generate an invoice")
            if start != locked.next_run_date:
                raise ValidationError("Billing date must match the billing schedule next run date")
            if charge_generator is generate_charge_from_schedule:
                charge = charge_generator(
                    user,
                    workspace,
                    locked,
                    charge_date=start,
                    post_ledger=False,
                )
            else:
                charge = charge_generator(user, workspace, locked, charge_date=start)

        invoice, created = generate_invoice_for_occupancy(
            user,
            workspace,
            locked.occupancy,
            billing_start=start,
            billing_end=period_end,
            due_date=due_date or period_end,
            ledger_event_type="recurring_invoice_generated",
            ledger_metadata={
                "billing_schedule_id": locked.pk,
                "billing_date": str(start),
                "charge_id": charge.pk,
            },
            rent_amount=0,
            charges_amount=charge.amount,
            allow_same_day_period=True,
        )

        # The charge ledger event is appended only after the invoice exists, so
        # the immutable event carries the canonical invoice relationship.
        post_ledger_event(
            user,
            workspace,
            event_type="charge_generated",
            event_key=f"charge:{charge.pk}:generated",
            occurred_at=charge.created_at,
            amount=charge.amount,
            invoice=invoice,
            occupancy=locked.occupancy,
            metadata={
                "charge_id": charge.pk,
                "charge_type": charge.charge_type,
                "billing_schedule_id": locked.pk,
                "billing_date": str(start),
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
