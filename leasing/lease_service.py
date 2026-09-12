from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.authorization import require_mutation_permission
from tenant.models import Occupancy

from .models import Lease


MUTABLE_FIELDS = {
    "agreement_number",
    "start_date",
    "end_date",
    "rent_amount",
    "security_deposit",
    "notice_period_days",
    "terms",
    "agreement_reference",
}

ALLOWED_TRANSITIONS = {
    Lease.STATUS_DRAFT: {
        Lease.STATUS_PENDING_SIGNATURE,
        Lease.STATUS_CANCELLED,
    },
    Lease.STATUS_PENDING_SIGNATURE: {
        Lease.STATUS_ACTIVE,
        Lease.STATUS_CANCELLED,
    },
    Lease.STATUS_ACTIVE: {
        Lease.STATUS_EXPIRED,
        Lease.STATUS_TERMINATED,
    },
    Lease.STATUS_EXPIRED: set(),
    Lease.STATUS_TERMINATED: set(),
    Lease.STATUS_CANCELLED: set(),
}


def _decimal(value, field_name):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"Invalid {field_name}")
    if parsed < 0:
        raise ValidationError(f"{field_name} cannot be negative")
    if parsed.as_tuple().exponent < -2:
        raise ValidationError(f"{field_name} must have at most 2 decimal places")
    return parsed


def _require_active_member(user, workspace):
    require_mutation_permission(user, workspace)


def _get_locked_occupancy(occupancy_id, workspace):
    try:
        return (
            Occupancy.objects.select_for_update()
            .select_related("tenant")
            .get(id=occupancy_id, tenant__workspace=workspace)
        )
    except (Occupancy.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Occupancy not found")


def _get_locked_lease(lease_id, workspace):
    try:
        return (
            Lease.objects.select_for_update()
            .select_related("occupancy__tenant")
            .get(id=lease_id, workspace=workspace)
        )
    except (Lease.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Lease not found")


def create_lease(user, workspace, data):
    """Create a Lease through the canonical P1.3 mutation boundary."""
    _require_active_member(user, workspace)

    data = dict(data or {})
    occupancy_value = data.pop("occupancy", None)
    occupancy_id = getattr(occupancy_value, "id", occupancy_value)
    if not occupancy_id:
        raise ValidationError("Occupancy required")

    with transaction.atomic():
        occupancy = _get_locked_occupancy(occupancy_id, workspace)

        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if not start_date or not end_date:
            raise ValidationError("Lease start and end dates are required")

        rent_amount = _decimal(data.get("rent_amount", occupancy.rent), "Rent amount")
        security_deposit = _decimal(
            data.get("security_deposit", occupancy.security_deposit or 0),
            "Security deposit",
        )

        allowed = {
            "agreement_number",
            "start_date",
            "end_date",
            "rent_amount",
            "security_deposit",
            "notice_period_days",
            "status",
            "terms",
            "agreement_reference",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError(f"Unsupported lease fields: {sorted(unknown)}")

        status = data.get("status", Lease.STATUS_DRAFT)
        if status not in Lease.VALID_STATUSES:
            raise ValidationError("Invalid lease status")
        if status != Lease.STATUS_DRAFT:
            raise ValidationError("New leases must start in draft status")

        lease = Lease(
            workspace=workspace,
            occupancy=occupancy,
            agreement_number=data.get("agreement_number", ""),
            start_date=start_date,
            end_date=end_date,
            rent_amount=rent_amount,
            security_deposit=security_deposit,
            notice_period_days=data.get("notice_period_days", 0),
            status=Lease.STATUS_DRAFT,
            terms=data.get("terms") or {},
            agreement_reference=data.get("agreement_reference", ""),
            created_by=user,
        )
        lease.save()
        return lease


def update_lease(user, workspace, lease_id, changes):
    """Update only P1.3-approved contractual Lease fields."""
    _require_active_member(user, workspace)
    changes = dict(changes or {})
    unsupported = set(changes) - MUTABLE_FIELDS
    if unsupported:
        raise ValidationError(f"Unsupported lease fields: {sorted(unsupported)}")
    if not changes:
        raise ValidationError("No lease changes supplied")

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        for field, value in changes.items():
            if field in {"rent_amount", "security_deposit"}:
                value = _decimal(value, field.replace("_", " ").title())
            setattr(lease, field, value)
        lease.updated_by = user
        lease.save()
        return lease


def transition_lease(user, workspace, lease_id, target_status):
    """Apply a validated Lease lifecycle transition atomically."""
    _require_active_member(user, workspace)
    if target_status not in Lease.VALID_STATUSES:
        raise ValidationError("Invalid lease status")

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        if lease.status == target_status:
            return lease

        allowed = ALLOWED_TRANSITIONS.get(lease.status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Invalid lease transition: {lease.status} -> {target_status}"
            )

        now = None
        if target_status == Lease.STATUS_ACTIVE:
            from django.utils import timezone
            now = timezone.now()
            lease.activated_at = now
        elif target_status == Lease.STATUS_TERMINATED:
            from django.utils import timezone
            now = timezone.now()
            lease.terminated_at = now
        elif target_status == Lease.STATUS_CANCELLED:
            from django.utils import timezone
            now = timezone.now()
            lease.cancelled_at = now

        lease.status = target_status
        lease.updated_by = user
        lease.save()
        return lease
