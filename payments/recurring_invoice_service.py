from .recurring_billing_service import generate_recurring_invoice


def generate_invoice_from_schedule(
    user,
    workspace,
    schedule,
    billing_date=None,
    due_date=None,
):
    """Compatibility facade for the canonical recurring billing orchestrator."""
    return generate_recurring_invoice(
        user,
        workspace,
        schedule,
        billing_date=billing_date,
        due_date=due_date,
    )
