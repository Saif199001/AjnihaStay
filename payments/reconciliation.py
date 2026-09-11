"""Read-only reconciliation between canonical financial sources and the ledger."""

from decimal import Decimal

from django.core.exceptions import ValidationError

from tenant.models import Occupancy

from .final_settlement import FinalSettlement
from .late_fee_models import LateFee
from .ledger_models import FinancialLedgerEntry
from .models import (
    AdvanceCredit,
    AdvanceCreditApplication,
    FinancialAdjustment,
    Invoice,
    Payment,
    PaymentAllocation,
)
from .refund_models import PaymentRefund

ZERO = Decimal("0.00")


def _finding(kind, event_type, event_key, detail, **extra):
    result = {
        "kind": kind,
        "event_type": event_type,
        "event_key": event_key,
        "detail": detail,
    }
    result.update(extra)
    return result


def _expected_for_workspace(workspace):
    expected = []

    for invoice in Invoice.objects.filter(occupancy__tenant__workspace=workspace).select_related("occupancy"):
        expected.append(("invoice_created", f"invoice:{invoice.pk}:created", invoice.total_amount, invoice.pk, None, invoice.occupancy_id))

    for payment in Payment.objects.filter(workspace=workspace):
        expected.append(("payment_recorded", f"payment:{payment.pk}:recorded", payment.amount, payment.invoice_id, payment.pk, getattr(payment, "occupancy_id", None)))

    for allocation in PaymentAllocation.objects.filter(payment__workspace=workspace).select_related("payment", "invoice__occupancy"):
        expected.append(("payment_allocated", f"payment-allocation:{allocation.pk}:created", allocation.amount, allocation.invoice_id, allocation.payment_id, allocation.invoice.occupancy_id))

    for credit in AdvanceCredit.objects.filter(workspace=workspace):
        expected.append(("advance_credit_created", f"advance-credit:{credit.pk}:created", credit.original_amount, None, credit.payment_id, credit.occupancy_id))

    for application in AdvanceCreditApplication.objects.filter(advance_credit__workspace=workspace).select_related("advance_credit__payment", "invoice__occupancy"):
        expected.append(("advance_credit_applied", f"advance-credit-application:{application.pk}:created", application.amount, application.invoice_id, application.advance_credit.payment_id, application.invoice.occupancy_id))

    for adjustment in FinancialAdjustment.objects.filter(workspace=workspace).select_related("invoice__occupancy"):
        expected.append(("adjustment_created", f"adjustment:{adjustment.pk}:created", adjustment.amount, adjustment.invoice_id, None, adjustment.invoice.occupancy_id))

    for charge in __import__("tenant.models", fromlist=["Charge"]).Charge.objects.filter(occupancy__tenant__workspace=workspace).select_related("occupancy"):
        expected.append(("charge_generated", f"charge:{charge.pk}:generated", charge.amount, charge.invoice_id if hasattr(charge, "invoice_id") else None, None, charge.occupancy_id))

    for late_fee in LateFee.objects.filter(workspace=workspace).select_related("invoice__occupancy"):
        expected.append(("late_fee_generated", f"late-fee:{late_fee.pk}:generated", late_fee.amount, late_fee.invoice_id, None, late_fee.invoice.occupancy_id))

    for settlement in FinalSettlement.objects.filter(workspace=workspace).select_related("occupancy"):
        amount = settlement.final_balance if settlement.final_balance > ZERO else None
        expected.append(("final_settlement_finalized", f"final-settlement:{settlement.pk}:finalized", amount, None, None, settlement.occupancy_id))

    for refund in PaymentRefund.objects.filter(workspace=workspace):
        expected.append(("refund_requested", f"refund:{refund.pk}:requested", refund.amount, refund.payment.invoice_id, refund.payment_id, getattr(refund.payment, "occupancy_id", None)))
        if refund.status == "processing":
            expected.append(("refund_processing", f"refund:{refund.pk}:processing", refund.amount, refund.payment.invoice_id, refund.payment_id, getattr(refund.payment, "occupancy_id", None)))
        elif refund.status == "succeeded":
            expected.append(("refund_succeeded", f"refund:{refund.pk}:succeeded", refund.amount, refund.payment.invoice_id, refund.payment_id, getattr(refund.payment, "occupancy_id", None)))
        elif refund.status == "failed":
            expected.append(("refund_failed", f"refund:{refund.pk}:failed", refund.amount, refund.payment.invoice_id, refund.payment_id, getattr(refund.payment, "occupancy_id", None)))

    return expected


def _source_exists(event):
    key = event.event_key
    if event.event_type == "invoice_created" and key.startswith("invoice:"):
        return Invoice.objects.filter(pk=key.split(":")[1], occupancy__tenant__workspace=event.workspace).exists()
    if event.event_type == "payment_recorded" and key.startswith("payment:"):
        return Payment.objects.filter(pk=key.split(":")[1], workspace=event.workspace).exists()
    mappings = {
        "payment_allocated": (PaymentAllocation, "payment__workspace"),
        "advance_credit_created": (AdvanceCredit, "workspace"),
        "advance_credit_applied": (AdvanceCreditApplication, "advance_credit__workspace"),
        "adjustment_created": (FinancialAdjustment, "workspace"),
        "charge_generated": (__import__("tenant.models", fromlist=["Charge"]).Charge, "occupancy__tenant__workspace"),
        "late_fee_generated": (LateFee, "workspace"),
        "final_settlement_finalized": (FinalSettlement, "workspace"),
    }
    if event.event_type in mappings:
        model, workspace_field = mappings[event.event_type]
        prefix = {
            "payment_allocated": "payment-allocation:",
            "advance_credit_created": "advance-credit:",
            "advance_credit_applied": "advance-credit-application:",
            "adjustment_created": "adjustment:",
            "charge_generated": "charge:",
            "late_fee_generated": "late-fee:",
            "final_settlement_finalized": "final-settlement:",
        }[event.event_type]
        if not key.startswith(prefix):
            return False
        try:
            pk = int(key.split(":")[1])
        except (ValueError, IndexError):
            return False
        return model.objects.filter(pk=pk, **{workspace_field: event.workspace}).exists()
    if event.event_type.startswith("refund_") and key.startswith("refund:"):
        try:
            pk = int(key.split(":")[1])
        except (ValueError, IndexError):
            return False
        return PaymentRefund.objects.filter(pk=pk, workspace=event.workspace).exists()
    return False


def ledger_reconciliation_report(*, workspace):
    """Return deterministic read-only reconciliation findings for one workspace."""
    findings = []
    expected = _expected_for_workspace(workspace)
    events = list(FinancialLedgerEntry.objects.filter(workspace=workspace).order_by("event_key", "pk"))
    by_key = {event.event_key: event for event in events}

    for event_type, event_key, amount, invoice_id, payment_id, occupancy_id in sorted(expected, key=lambda item: item[1]):
        event = by_key.get(event_key)
        if event is None:
            findings.append(_finding("missing_event", event_type, event_key, "Expected financial event is missing."))
            continue
        if event.event_type != event_type:
            findings.append(_finding("unexpected_event", event_type, event_key, "Ledger event type does not match the expected source event.", actual_event_type=event.event_type))
        if amount is None:
            if event.amount is not None:
                findings.append(_finding("amount_mismatch", event_type, event_key, "Expected no monetary amount for this event.", expected_amount=None, actual_amount=event.amount))
        elif event.amount != amount:
            findings.append(_finding("amount_mismatch", event_type, event_key, "Ledger amount does not match the canonical source amount.", expected_amount=amount, actual_amount=event.amount))
        if event.invoice_id != invoice_id or event.payment_id != payment_id or event.occupancy_id != occupancy_id:
            findings.append(_finding("relationship_mismatch", event_type, event_key, "Ledger source relationships do not match the canonical source.", expected_invoice_id=invoice_id, actual_invoice_id=event.invoice_id, expected_payment_id=payment_id, actual_payment_id=event.payment_id, expected_occupancy_id=occupancy_id, actual_occupancy_id=event.occupancy_id))

    for event in events:
        if not _source_exists(event):
            findings.append(_finding("orphan_event", event.event_type, event.event_key, "Ledger event has no matching canonical source in this workspace."))

    return {
        "workspace_id": workspace.pk,
        "ok": not findings,
        "finding_count": len(findings),
        "findings": findings,
    }
