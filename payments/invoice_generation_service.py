from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from tenant.models import Charge, Occupancy

from .models import Invoice


def _parse_date(value, field_name):
    if isinstance(value, date):
        return value
    if value in (None, ""):
        raise ValidationError(f"{field_name} is required")
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name}")


def _resolve_occupancy(occupancy, workspace):
    occupancy_id = getattr(occupancy, "id", occupancy)
    try:
        occupancy_id = int(occupancy_id)
    except (TypeError, ValueError):
        raise ValidationError("Invalid occupancy ID")
    if occupancy_id <= 0:
        raise ValidationError("Invalid occupancy ID")
    try:
        return Occupancy.objects.select_for_update().select_related("tenant").get(
            id=occupancy_id,
            tenant__workspace=workspace,
        )
    except Occupancy.DoesNotExist:
        raise ValidationError("Occupancy not found")


def generate_invoice_for_occupancy(
    user,
    workspace,
    occupancy,
    billing_start,
    billing_end,
    due_date=None,
):
    """Generate one canonical invoice for an occupancy billing period.

    This service owns invoice creation only. It never creates payments,
    allocations, or advances recurring-billing cursors.
    """
    del user  # Kept in the contract for future audit attribution.

    billing_start = _parse_date(billing_start, "billing start date")
    billing_end = _parse_date(billing_end, "billing end date")
    due_date = _parse_date(due_date or billing_start, "due date")

    if billing_end <= billing_start:
        raise ValidationError("Billing end date must be after billing start date")

    with transaction.atomic():
        occupancy = _resolve_occupancy(occupancy, workspace)

        if not occupancy.is_active:
            raise ValidationError("Inactive occupancy cannot generate an invoice")
        if billing_start < occupancy.check_in_date:
            raise ValidationError("Billing start date cannot be before occupancy check-in date")
        if occupancy.check_out_date and billing_end > occupancy.check_out_date:
            raise ValidationError("Billing end date cannot be after occupancy check-out date")
        if due_date < billing_start:
            raise ValidationError("Due date cannot be before billing start date")

        existing_invoice = Invoice.objects.filter(
            occupancy=occupancy,
            billing_start=billing_start,
            billing_end=billing_end,
        ).first()
        if existing_invoice:
            return existing_invoice, False

        charges_amount = (
            Charge.objects.filter(
                occupancy=occupancy,
                charge_date__gte=billing_start,
                charge_date__lt=billing_end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        invoice = Invoice.objects.create(
            occupancy=occupancy,
            billing_start=billing_start,
            billing_end=billing_end,
            rent_amount=occupancy.rent,
            charges_amount=charges_amount,
            due_date=due_date,
        )
        return invoice, True
