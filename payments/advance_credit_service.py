from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from tenant.models import Occupancy, Tenant

from .adjustment_service import calculate_invoice_financial_position
from .allocation_service import get_payment_available_allocation_amount
from .authorization import require_mutation_permission
from .models import AdvanceCredit, AdvanceCreditApplication, Invoice, Payment
from .services import recalculate_invoice_state


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
    require_mutation_permission(user, workspace)
    payment_id = _positive_id(data.get("source_payment", data.get("payment")), "source payment")
    tenant_id = _positive_id(data.get("tenant"), "tenant")
    amount = _positive_decimal(data.get("amount"), "advance credit")
    occupancy_value = data.get("occupancy")
    occupancy_id = None if occupancy_value in (None, "") else _positive_id(occupancy_value, "occupancy")

    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(id=payment_id, workspace=workspace)
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
                    id=occupancy_id, tenant__workspace=workspace
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

        credit = AdvanceCredit.objects.create(
            workspace=workspace,
            tenant=tenant,
            occupancy=occupancy,
            source_payment=payment,
            original_amount=amount,
        )
        from .ledger_service import post_ledger_event
        post_ledger_event(
            user,
            workspace,
            event_type="advance_credit_created",
            event_key=f"advance-credit:{credit.pk}:created",
            occurred_at=credit.created_at,
            amount=credit.original_amount,
            payment=payment,
            occupancy=occupancy,
            metadata={"advance_credit_id": credit.pk},
        )
        return credit


def get_advance_credit_applied_amount(credit):
    """Return the canonical amount of a credit already consumed by applications."""
    return (
        AdvanceCreditApplication.objects.filter(credit=credit)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


def get_advance_credit_available_amount(credit):
    """Return the credit balance derived from immutable applications."""
    return max(
        credit.original_amount - get_advance_credit_applied_amount(credit),
        Decimal("0"),
    )


def get_advance_credits(workspace):
    """Return workspace-scoped advance credits with application data ready for serialization."""
    return (
        AdvanceCredit.objects.filter(workspace=workspace)
        .select_related("tenant", "occupancy", "source_payment")
        .prefetch_related("applications")
        .order_by("-created_at", "-id")
    )


def get_advance_credit(credit_id, workspace):
    """Return one workspace-scoped advance credit or raise a not-found validation error."""
    try:
        credit_id = _positive_id(credit_id, "advance credit")
        return (
            AdvanceCredit.objects.filter(workspace=workspace)
            .select_related("tenant", "occupancy", "source_payment")
            .prefetch_related("applications")
            .get(id=credit_id)
        )
    except AdvanceCredit.DoesNotExist:
        raise ValidationError("Advance credit not found")


def apply_advance_credit(user, workspace, data):
    """Apply prepaid credit to an invoice through the canonical settlement service."""
    require_mutation_permission(user, workspace)
    credit_id = _positive_id(data.get("credit"), "advance credit")
    invoice_id = _positive_id(data.get("invoice"), "invoice")
    amount = _positive_decimal(data.get("amount"), "advance credit application")

    with transaction.atomic():
        try:
            credit = AdvanceCredit.objects.select_for_update().get(id=credit_id, workspace=workspace)
        except AdvanceCredit.DoesNotExist:
            raise ValidationError("Advance credit not found")
        try:
            invoice = Invoice.objects.select_for_update().select_related("occupancy__tenant").get(
                id=invoice_id, occupancy__tenant__workspace=workspace
            )
        except Invoice.DoesNotExist:
            raise ValidationError("Invoice not found")

        if credit.tenant_id != invoice.occupancy.tenant_id:
            raise ValidationError("Advance credit and invoice must belong to the same tenant")
        available_credit = get_advance_credit_available_amount(credit)
        if amount > available_credit:
            raise ValidationError("Advance credit application exceeds available credit")
        position = calculate_invoice_financial_position(invoice)
        if amount > position["outstanding"]:
            raise ValidationError("Advance credit application exceeds invoice outstanding amount")

        application = AdvanceCreditApplication.objects.create(credit=credit, invoice=invoice, amount=amount)
        invoice = recalculate_invoice_state(invoice)
        from .ledger_service import post_ledger_event
        post_ledger_event(
            user,
            workspace,
            event_type="advance_credit_applied",
            event_key=f"advance-credit-application:{application.pk}:created",
            occurred_at=application.created_at,
            amount=application.amount,
            invoice=invoice,
            payment=credit.source_payment,
            occupancy=invoice.occupancy,
            metadata={"advance_credit_id": credit.pk, "application_id": application.pk},
        )
        return application, get_advance_credit_available_amount(credit), invoice
