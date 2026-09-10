from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Charge, Occupancy


def _decimal_amount(value, field_name="Amount"):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError(f"{field_name} must be a valid amount")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(f"{field_name} must be greater than zero")
    return amount.quantize(Decimal("0.01"))


def _date_value(value, field_name):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name}")


def prorate_amount(amount, period_start, period_end, active_start, active_end=None):
    """Calculate a calendar-day prorated amount for an occupancy in a billing period."""
    amount = _decimal_amount(amount)
    period_start = _date_value(period_start, "period start")
    period_end = _date_value(period_end, "period end")
    active_start = _date_value(active_start, "active start")
    active_end = _date_value(active_end, "active end") if active_end else period_end
    if period_end < period_start:
        raise ValidationError("Period end date cannot be before period start date")

    overlap_start = max(period_start, active_start)
    overlap_end = min(period_end, active_end)
    if overlap_end < overlap_start:
        return Decimal("0.00")

    period_days = Decimal((period_end - period_start).days + 1)
    active_days = Decimal((overlap_end - overlap_start).days + 1)
    return (amount * active_days / period_days).quantize(Decimal("0.01"))


def _validate_occupancy(occupancy, workspace, *, lock=False):
    occupancy_id = getattr(occupancy, "id", occupancy)
    try:
        occupancy_id = int(occupancy_id)
    except (TypeError, ValueError):
        raise ValidationError("Occupancy not found")
    if occupancy_id <= 0:
        raise ValidationError("Occupancy not found")
    queryset = Occupancy.objects.select_related("tenant")
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(id=occupancy_id, tenant__workspace=workspace)
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")


def create_charge(
    user,
    workspace,
    *,
    occupancy,
    charge_type,
    amount,
    charge_date,
    description=None,
    update_invoice=True,
    invoice=None,
):
    """Create a workspace-scoped charge, optionally updating a specific active invoice atomically."""
    from payments.authorization import require_mutation_permission

    require_mutation_permission(user, workspace)
    charge_date = _date_value(charge_date, "charge date")
    amount = _decimal_amount(amount)

    with transaction.atomic():
        occupancy = _validate_occupancy(occupancy, workspace, lock=True)
        if not occupancy.is_active:
            raise ValidationError("Inactive occupancy cannot receive a charge")
        if charge_date < occupancy.check_in_date:
            raise ValidationError("Charge date cannot be before occupancy check-in date")
        if occupancy.check_out_date and charge_date > occupancy.check_out_date:
            raise ValidationError("Charge date cannot be after occupancy check-out date")

        target_invoice = None
        if update_invoice:
            if invoice is not None:
                invoice_id = getattr(invoice, "id", invoice)
                try:
                    invoice_id = int(invoice_id)
                except (TypeError, ValueError):
                    raise ValidationError("Invoice not found")
                if invoice_id <= 0:
                    raise ValidationError("Invoice not found")
                target_invoice = occupancy.invoices.select_for_update().filter(
                    id=invoice_id,
                    status="pending",
                ).first()
                if not target_invoice:
                    raise ValidationError("Invoice not found or is not pending")
            else:
                target_invoice = occupancy.invoices.select_for_update().filter(
                    status="pending"
                ).last()
                if not target_invoice:
                    raise ValidationError("No active invoice found")

        charge = Charge.objects.create(
            occupancy=occupancy,
            charge_type=charge_type,
            amount=amount,
            charge_date=charge_date,
            description=description,
        )
        if target_invoice is not None:
            target_invoice.charges_amount += amount
            target_invoice.total_amount = target_invoice.rent_amount + target_invoice.charges_amount
            target_invoice.save()
        return charge


def create_prorated_charge(
    user,
    workspace,
    *,
    occupancy,
    charge_type,
    period_amount,
    period_start,
    period_end,
    description=None,
):
    """Create a charge prorated to active occupancy days and apply it to the active invoice."""
    period_start = _date_value(period_start, "period start")
    period_end = _date_value(period_end, "period end")
    occupancy_obj = _validate_occupancy(occupancy, workspace)
    amount = prorate_amount(
        period_amount,
        period_start,
        period_end,
        occupancy_obj.check_in_date,
        occupancy_obj.check_out_date,
    )
    if amount <= 0:
        raise ValidationError("No active occupancy days in billing period")
    charge_date = min(max(occupancy_obj.check_in_date, period_start), period_end)
    return create_charge(
        user,
        workspace,
        occupancy=occupancy_obj,
        charge_type=charge_type,
        amount=amount,
        charge_date=charge_date,
        description=description,
    )
