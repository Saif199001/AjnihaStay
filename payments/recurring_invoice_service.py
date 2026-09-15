"""Backward-compatible recurring invoice entry point.

The implementation intentionally lives in recurring_billing_service so there is
one authoritative atomic charge + invoice orchestration boundary.
"""

from django.core.exceptions import ValidationError

from .recurring_billing_service import generate_recurring_billing_occurrence


def generate_invoice_from_schedule(user, workspace, schedule, billing_date=None, due_date=None):
    """Compatibility wrapper around the canonical recurring billing command."""
    if billing_date is None:
        raise ValidationError("Billing date is required")
    result = generate_recurring_billing_occurrence(
        user,
        workspace,
        schedule,
        occurrence_date=billing_date,
        due_date=due_date,
    )
    return result["invoice"]
