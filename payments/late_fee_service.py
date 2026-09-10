from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from .adjustment_service import calculate_invoice_financial_position
from .authorization import require_mutation_permission
from .late_fee_models import LateFee, LateFeePolicy
from .models import Invoice

TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _effective_date(invoice, policy):
    return invoice.due_date + timedelta(days=policy.grace_period_days + 1)


def calculate_late_fee(invoice, policy, as_of):
    """Calculate a deterministic one-time late fee without mutating state."""
    effective_date = _effective_date(invoice, policy)
    if not policy.enabled or as_of < effective_date:
        return effective_date, Decimal("0.00"), None

    position = calculate_invoice_financial_position(invoice)
    outstanding = _money(position["outstanding"])
    if outstanding < policy.minimum_overdue_balance or outstanding <= 0:
        return effective_date, Decimal("0.00"), outstanding

    if policy.calculation_mode == LateFeePolicy.MODE_FIXED:
        fee = _money(policy.rate)
    else:
        fee = _money(outstanding * policy.rate / Decimal("100"))

    if policy.maximum_late_fee is not None:
        fee = min(fee, _money(policy.maximum_late_fee))
    return effective_date, max(fee, Decimal("0.00")), outstanding


def generate_late_fee(user, workspace, invoice_id, as_of=None):
    """Generate one immutable late-fee fact for an overdue invoice."""
    require_mutation_permission(user, workspace)
    from django.utils import timezone
    as_of = as_of or timezone.localdate()

    with transaction.atomic():
        from workspaces.models import Workspace
        workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
        try:
            invoice = Invoice.objects.select_for_update().select_related(
                "occupancy__tenant"
            ).get(id=invoice_id, occupancy__tenant__workspace=workspace)
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        try:
            policy = LateFeePolicy.objects.select_for_update().get(workspace=workspace)
        except LateFeePolicy.DoesNotExist:
            raise ValidationError("Late fee policy is not configured")

        effective_date, fee, outstanding = calculate_late_fee(invoice, policy, as_of)
        if fee <= 0:
            return None, {
                "created": False,
                "eligible": False,
                "effective_date": effective_date,
                "amount": Decimal("0.00"),
                "outstanding": outstanding,
            }

        existing = LateFee.objects.filter(
            workspace=workspace,
            invoice=invoice,
            policy=policy,
            effective_date=effective_date,
        ).first()
        if existing:
            return existing, {"created": False, "eligible": True, "effective_date": effective_date, "amount": existing.amount, "outstanding": existing.outstanding_balance}

        late_fee = LateFee.objects.create(
            workspace=workspace,
            invoice=invoice,
            policy=policy,
            effective_date=effective_date,
            amount=fee,
            outstanding_balance=outstanding,
            calculation_mode=policy.calculation_mode,
            reason=f"Late fee for invoice {invoice.invoice_number}",
            created_by=user,
        )

        return late_fee, {
            "created": True,
            "eligible": True,
            "effective_date": effective_date,
            "amount": fee,
            "outstanding": outstanding,
        }
