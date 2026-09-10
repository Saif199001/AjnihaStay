"""Canonical financial mutation boundary for AjnihaStay.

Public domain services remain backward-compatible entry points, but new financial
commands should enter through this module. The module deliberately delegates to
existing transactional implementations until each bounded transition is migrated
into this service in later P0 milestones.
"""

from enum import Enum


class FinancialTransition(str, Enum):
    CREATE_INVOICE = "create_invoice"
    RECORD_PAYMENT = "record_payment"
    ALLOCATE_PAYMENT = "allocate_payment"
    CREATE_ADVANCE_CREDIT = "create_advance_credit"
    APPLY_ADVANCE_CREDIT = "apply_advance_credit"
    CREATE_ADJUSTMENT = "create_adjustment"
    CREATE_BILLING_SCHEDULE = "create_billing_schedule"
    UPDATE_BILLING_SCHEDULE = "update_billing_schedule"
    GENERATE_CHARGE = "generate_charge"
    GENERATE_RECURRING_INVOICE = "generate_recurring_invoice"
    REFRESH_INVOICE_LIFECYCLE = "refresh_invoice_lifecycle"
    GENERATE_LATE_FEE = "generate_late_fee"
    SETTLE_OCCUPANCY = "settle_occupancy"


def transition_name(transition):
    """Return a stable string name for a financial transition."""
    if isinstance(transition, FinancialTransition):
        return transition.value
    try:
        return FinancialTransition(transition).value
    except ValueError as exc:
        raise ValueError(f"Unsupported financial transition: {transition}") from exc


def execute_transition(transition, *, user, workspace, **payload):
    """Execute a supported financial mutation through the canonical boundary."""
    transition = FinancialTransition(transition)

    if transition is FinancialTransition.CREATE_INVOICE:
        from .services import create_invoice
        return create_invoice(user, workspace, payload["data"])
    if transition is FinancialTransition.RECORD_PAYMENT:
        from .services import record_payment
        return record_payment(user, workspace, payload["data"])
    if transition is FinancialTransition.ALLOCATE_PAYMENT:
        from .allocation_service import allocate_payment
        return allocate_payment(user, workspace, payload["payment"], payload["allocations"])
    if transition is FinancialTransition.CREATE_ADVANCE_CREDIT:
        from .advance_credit_service import create_advance_credit
        return create_advance_credit(user, workspace, payload["data"])
    if transition is FinancialTransition.APPLY_ADVANCE_CREDIT:
        from .advance_credit_service import apply_advance_credit
        return apply_advance_credit(user, workspace, payload["data"])
    if transition is FinancialTransition.CREATE_ADJUSTMENT:
        from .adjustment_service import create_financial_adjustment
        return create_financial_adjustment(user, workspace, payload["data"])
    if transition is FinancialTransition.CREATE_BILLING_SCHEDULE:
        from .billing_service import create_billing_schedule
        return create_billing_schedule(user, workspace, payload["data"])
    if transition is FinancialTransition.UPDATE_BILLING_SCHEDULE:
        from .billing_service import update_billing_schedule
        return update_billing_schedule(user, workspace, payload["schedule_id"], payload["data"])
    if transition is FinancialTransition.GENERATE_CHARGE:
        from .charge_generation_service import generate_charge_from_schedule
        return generate_charge_from_schedule(user, workspace, payload["schedule"], payload["charge_date"])
    if transition is FinancialTransition.GENERATE_RECURRING_INVOICE:
        from .recurring_invoice_service import generate_invoice_from_schedule
        return generate_invoice_from_schedule(user, workspace, payload["schedule"], payload.get("billing_date"), payload.get("due_date"))
    if transition is FinancialTransition.REFRESH_INVOICE_LIFECYCLE:
        from .invoice_lifecycle_service import refresh_invoice_lifecycle
        return refresh_invoice_lifecycle(payload["invoice_id"], workspace, as_of=payload.get("as_of"))
    if transition is FinancialTransition.GENERATE_LATE_FEE:
        from .late_fee_service import generate_late_fee
        return generate_late_fee(user, workspace, payload["invoice_id"], as_of=payload.get("as_of"))
    if transition is FinancialTransition.SETTLE_OCCUPANCY:
        from .settlement_service import settle_occupancy
        return settle_occupancy(
            user,
            workspace,
            payload["occupancy_id"],
            payload["outcome"],
            payload.get("refundable_deposit"),
        )
    raise ValueError(f"Unsupported financial transition: {transition}")
