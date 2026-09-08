from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import Payment
from .refund_models import PaymentRefund


REFUND_AUTHORIZED_ROLES = {"owner", "admin", "manager"}
ACTIVE_REFUND_STATUSES = {
    PaymentRefund.STATUS_REQUESTED,
    PaymentRefund.STATUS_PROCESSING,
}


def _workspace_id(workspace):
    return getattr(workspace, "id", workspace)


def _is_authorized(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = getattr(user, "role", None)
    if role in REFUND_AUTHORIZED_ROLES:
        return True
    return False


def _parse_amount(value):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Invalid refund amount")
    if amount <= 0:
        raise ValidationError("Refund amount must be greater than zero")
    return amount.quantize(Decimal("0.01"))


def _get_payment_for_workspace(payment_value, workspace):
    payment_id = getattr(payment_value, "id", payment_value)
    try:
        payment_id = int(payment_id)
    except (TypeError, ValueError):
        raise ValidationError("Invalid payment ID")
    if payment_id <= 0:
        raise ValidationError("Invalid payment ID")
    try:
        return Payment.objects.select_for_update().get(
            id=payment_id,
            workspace_id=_workspace_id(workspace),
        )
    except Payment.DoesNotExist:
        raise ValidationError("Payment not found")


def _refund_capacity(payment):
    successful = (
        PaymentRefund.objects.filter(
            payment=payment,
            status=PaymentRefund.STATUS_SUCCEEDED,
        ).aggregate_total()["total"]
        if False
        else None
    )
    successful = sum(
        (refund.amount for refund in PaymentRefund.objects.filter(
            payment=payment,
            status=PaymentRefund.STATUS_SUCCEEDED,
        )),
        Decimal("0"),
    )
    reserved = sum(
        (refund.amount for refund in PaymentRefund.objects.filter(
            payment=payment,
            status__in=ACTIVE_REFUND_STATUSES,
        )),
        Decimal("0"),
    )
    return max(payment.amount - successful - reserved, Decimal("0"))


def request_payment_refund(
    *, user, workspace, payment, amount, reason, reference=None, idempotency_key=None
):
    """Canonical financial transition for requesting a payment refund.

    The payment row is locked while refundable capacity is checked and the
    immutable refund event is created. Payment and allocation records are not
    mutated here.
    """
    if not _is_authorized(user):
        raise ValidationError("User is not authorized to request refunds")

    amount = _parse_amount(amount)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Refund reason is required")

    workspace_id = _workspace_id(workspace)

    with transaction.atomic():
        payment_obj = _get_payment_for_workspace(payment, workspace)

        if idempotency_key:
            existing = PaymentRefund.objects.filter(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
            ).first()
            if existing:
                if existing.payment_id != payment_obj.id or existing.amount != amount:
                    raise ValidationError("Idempotency key conflicts with existing refund")
                return existing

        capacity = _refund_capacity(payment_obj)
        if amount > capacity:
            raise ValidationError("Refund amount exceeds refundable capacity")

        try:
            return PaymentRefund.objects.create(
                workspace=workspace,
                payment=payment_obj,
                amount=amount,
                status=PaymentRefund.STATUS_REQUESTED,
                reason=reason,
                reference=reference,
                idempotency_key=idempotency_key,
                requested_by=user,
            )
        except IntegrityError:
            if idempotency_key:
                existing = PaymentRefund.objects.filter(
                    workspace_id=workspace_id,
                    idempotency_key=idempotency_key,
                ).first()
                if existing and existing.payment_id == payment_obj.id and existing.amount == amount:
                    return existing
            raise


def transition_payment_refund(*, user, workspace, refund, status, failure_reason=None):
    """Apply an allowed provider/state transition to an existing refund event."""
    if not _is_authorized(user):
        raise ValidationError("User is not authorized to transition refunds")

    allowed = {
        PaymentRefund.STATUS_REQUESTED,
        PaymentRefund.STATUS_PROCESSING,
        PaymentRefund.STATUS_SUCCEEDED,
        PaymentRefund.STATUS_FAILED,
    }
    if status not in allowed:
        raise ValidationError("Invalid refund status")

    with transaction.atomic():
        try:
            refund_obj = PaymentRefund.objects.select_for_update().get(
                id=getattr(refund, "id", refund),
                workspace_id=_workspace_id(workspace),
            )
        except PaymentRefund.DoesNotExist:
            raise ValidationError("Refund not found")

        if status == refund_obj.status:
            return refund_obj

        transitions = {
            PaymentRefund.STATUS_REQUESTED: {
                PaymentRefund.STATUS_PROCESSING,
                PaymentRefund.STATUS_FAILED,
            },
            PaymentRefund.STATUS_PROCESSING: {
                PaymentRefund.STATUS_SUCCEEDED,
                PaymentRefund.STATUS_FAILED,
            },
            PaymentRefund.STATUS_SUCCEEDED: set(),
            PaymentRefund.STATUS_FAILED: set(),
        }
        if status not in transitions[refund_obj.status]:
            raise ValidationError("Invalid refund state transition")

        refund_obj.status = status
        if status == PaymentRefund.STATUS_FAILED:
            refund_obj.failure_reason = (failure_reason or "").strip()
            if not refund_obj.failure_reason:
                raise ValidationError("Refund failure reason is required")
        elif failure_reason is not None:
            raise ValidationError("Failure reason is only valid for failed refunds")

        refund_obj.save()
        return refund_obj
