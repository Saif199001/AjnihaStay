from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .authorization import require_mutation_permission
from .ledger_models import FinancialLedgerEntry


_IMMUTABLE_COMPARISON_FIELDS = (
    "event_type",
    "event_key",
    "amount",
    "currency",
    "invoice_id",
    "payment_id",
    "occupancy_id",
    "created_by_id",
    "metadata",
)


def _normalise_amount(amount):
    if amount in (None, ""):
        return None
    try:
        value = Decimal(str(amount))
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid ledger amount")
    if value <= 0:
        raise ValidationError("Ledger amount must be greater than zero")
    if value.as_tuple().exponent < -2:
        raise ValidationError("Ledger amount must use at most two decimal places")
    return value.quantize(Decimal("0.01"))


def _normalise_event_key(event_key):
    value = str(event_key or "").strip()
    if not value:
        raise ValidationError("Ledger event key is required")
    if len(value) > 160:
        raise ValidationError("Ledger event key is too long")
    return value


def _normalise_currency(currency):
    value = str(currency or "INR").strip().upper()
    if len(value) != 3:
        raise ValidationError("Ledger currency must be a 3-letter code")
    return value


def _validate_event_type(event_type):
    allowed = {value for value, _label in FinancialLedgerEntry.EVENT_TYPES}
    if event_type not in allowed:
        raise ValidationError(f"Unsupported ledger event type: {event_type}")
    return event_type


def _same_event(existing, candidate):
    return all(
        getattr(existing, field) == getattr(candidate, field)
        for field in _IMMUTABLE_COMPARISON_FIELDS
    )


def post_ledger_event(
    user,
    workspace,
    *,
    event_type,
    event_key,
    occurred_at,
    amount=None,
    currency="INR",
    invoice=None,
    payment=None,
    occupancy=None,
    metadata=None,
):
    """Append one immutable ledger event through the canonical posting boundary.

    This service records an already-authorized financial fact. It never changes
    Invoice, Payment, allocation, credit, adjustment, or settlement state.
    Replaying the same workspace/event key with the same effect returns the
    original row; reusing it for a different effect is a deterministic conflict.
    """
    require_mutation_permission(user, workspace)

    event_type = _validate_event_type(event_type)
    event_key = _normalise_event_key(event_key)
    amount = _normalise_amount(amount)
    currency = _normalise_currency(currency)
    metadata = dict(metadata or {})

    candidate = FinancialLedgerEntry(
        workspace=workspace,
        event_type=event_type,
        event_key=event_key,
        occurred_at=occurred_at,
        amount=amount,
        currency=currency,
        invoice=invoice,
        payment=payment,
        occupancy=occupancy,
        created_by=user,
        metadata=metadata,
    )

    # Model-level workspace/reference validation happens before insertion. The
    # source objects are intentionally not mutated here.
    candidate.clean()

    with transaction.atomic():
        try:
            existing = (
                FinancialLedgerEntry.objects.select_for_update()
                .get(workspace=workspace, event_key=event_key)
            )
        except FinancialLedgerEntry.DoesNotExist:
            try:
                return FinancialLedgerEntry.objects.create(
                    workspace=workspace,
                    event_type=event_type,
                    event_key=event_key,
                    occurred_at=occurred_at,
                    amount=amount,
                    currency=currency,
                    invoice=invoice,
                    payment=payment,
                    occupancy=occupancy,
                    created_by=user,
                    metadata=metadata,
                )
            except IntegrityError:
                # A concurrent writer may have inserted the same key after the
                # initial lookup. Retry inside a savepoint, then apply replay or
                # conflict semantics against the committed winner.
                try:
                    existing = (
                        FinancialLedgerEntry.objects.select_for_update()
                        .get(workspace=workspace, event_key=event_key)
                    )
                except FinancialLedgerEntry.DoesNotExist:
                    raise

        if _same_event(existing, candidate):
            return existing
        raise ValidationError("Ledger event key already exists for a different financial event")
