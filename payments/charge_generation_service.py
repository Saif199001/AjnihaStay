from django.core.exceptions import ValidationError

from .recurring_billing_service import generate_recurring_charge


def generate_charge_from_schedule(user, workspace, schedule, charge_date=None):
    """Compatibility facade for the canonical recurring billing orchestrator."""
    if charge_date is None:
        raise ValidationError("Charge date is required")
    return generate_recurring_charge(user, workspace, schedule, charge_date)
