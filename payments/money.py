"""Canonical monetary input validation for financial mutation boundaries."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


MONEY_QUANTUM = Decimal("0.01")


def normalize_money(value, field_name, *, allow_zero=False):
    """Parse a money value without allowing implicit DecimalField rounding."""
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError(f"Invalid {field_name} amount")

    if not amount.is_finite():
        raise ValidationError(f"Invalid {field_name} amount")
    if allow_zero:
        if amount < 0:
            raise ValidationError(f"{field_name.capitalize()} amount cannot be negative")
    elif amount <= 0:
        raise ValidationError(f"{field_name.capitalize()} amount must be greater than zero")

    if amount != amount.quantize(MONEY_QUANTUM):
        raise ValidationError(
            f"{field_name.capitalize()} amount cannot have more than two decimal places"
        )
    return amount
