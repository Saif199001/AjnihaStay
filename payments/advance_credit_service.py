from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from tenant.models import Occupancy, Tenant

from .allocation_service import get_payment_available_allocation_amount
from .models import AdvanceCredit, Payment


def _positive_decimal(value, field_name):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError(f"Invalid {field_name} amount")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(f"{field_name.capitalize()} amount must be greater than zero")
    return amount


def _positive_id(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name} ID")
    if parsed <= 0:
        raise ValidationError(f"Invalid {field_name} ID")
    return parsed


def create_advance_credit(user, workspace, data):
    """Create an explicit prepaid credit from currently unallocated payment capacity."""
    payment_id = _positive_id(data.get("source_payment", data.get("payment")), "source payment")
    tenant_id = _positive_id(data.get("tenant"), "tenant")
    amount = _positive_decimal(data.get("amount"), "advance credit")

    occupancy_value = data.get("occupancy")
    occupancy_id = None if occupancy_value in (None, "") else _positive_id(occupancy_value, "occupancy")

    with transaction.atomic():
        try:
            # Lock the payment row itself. Do not select_related through the nullable
            # invoice FK: PostgreSQL cannot apply FOR UPDATE to the nullable side
            # of an outer join.
            payment = Payment.objects.select_for_update().get(
                id=payment_id,
                workspace=workspace,
            )
        except Payment.DoesNotExist:
            raise ValidationError("Payment not found")

        try:
            tenant = Tenant.objects.get(id=tenant_id, workspace=workspace)
        except Tenant.DoesNotExist:
            raise ValidationError("Tenant not found")

        occupancy = None
        if occupancy_id:
            try:
                occupancy = Occupancy.objects.select_related("tenant").get(
                    id=occupancy_id,
                    tenant__workspace=workspace,
                )
            except Occupancy.DoesNotExist:
                raise ValidationError("Occupancy not found")
            if occupancy.tenant_id != tenant.id:
                raise ValidationError("Advance credit occupancy must belong to the selected tenant")

        if payment.invoice_id:
            try:
                payment_invoice = payment.invoice
                payment_invoice_tenant_id = payment_invoice.occupancy.tenant_id
            except (AttributeError, Occupancy.DoesNotExist):
                raise ValidationError("Payment invoice is invalid")
            if payment_invoice_tenant_id != tenant.id:
                raise ValidationError("Advance credit tenant must match the payment invoice tenant")

        if AdvanceCredit.objects.filter(source_payment=payment).exists():
            raise ValidationError("Advance credit already exists for this source payment")

        available_capacity = get_payment_available_allocation_amount(payment)
        if amount > available_capacity:
            raise ValidationError("Advance credit exceeds available payment capacity")

        return AdvanceCredit.objects.create(
            workspace=workspace,
            tenant=tenant,
            occupancy=occupancy,
            source_payment=payment,
            original_amount=amount,
        )
