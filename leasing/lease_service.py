from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.authorization import require_mutation_permission
from tenant.models import Occupancy

from .lifecycle_event_service import append_lifecycle_event
from .lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent
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

IMMUTABLE_CONTRACT_STATUSES = {
    Lease.STATUS_ACTIVE,
    Lease.STATUS_EXPIRED,
    Lease.STATUS_TERMINATED,
    Lease.STATUS_CANCELLED,
}

ALLOWED_TRANSITIONS = {
    Lease.STATUS_DRAFT: {
        Lease.STATUS_PENDING_SIGNATURE,
    },
    Lease.STATUS_PENDING_SIGNATURE: {
        Lease.STATUS_ACTIVE,
    },
    Lease.STATUS_ACTIVE: set(),
    Lease.STATUS_EXPIRED: set(),
    Lease.STATUS_TERMINATED: set(),
    Lease.STATUS_CANCELLED: set(),
}

STATUS_EVENT_TYPES = {
    Lease.STATUS_PENDING_SIGNATURE: LeaseLifecycleEvent.EVENT_PENDING_SIGNATURE,
    Lease.STATUS_ACTIVE: LeaseLifecycleEvent.EVENT_ACTIVATED,
    Lease.STATUS_EXPIRED: LeaseLifecycleEvent.EVENT_EXPIRED,
    Lease.STATUS_TERMINATED: LeaseLifecycleEvent.EVENT_TERMINATED,
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


def _ensure_active_contract_version(lease):
    existing = LeaseContractVersion.objects.filter(lease=lease, version_number=1).first()
    if existing:
        return existing
    return LeaseContractVersion.objects.create(
        lease=lease,
        workspace=lease.workspace,
        version_number=1,
        start_date=lease.start_date,
        end_date=lease.end_date,
        rent_amount=lease.rent_amount,
        security_deposit=lease.security_deposit,
        notice_period_days=lease.notice_period_days,
        terms=dict(lease.terms or {}),
        agreement_reference=lease.agreement_reference,
        created_by=lease.created_by,
    )


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
        append_lifecycle_event(
            lease=lease,
            event_type=LeaseLifecycleEvent.EVENT_CREATED,
            actor=user,
            occurred_at=lease.created_at,
            effective_date=lease.start_date,
            metadata={"status": Lease.STATUS_DRAFT},
            event_key=LeaseLifecycleEvent.EVENT_CREATED,
        )
        return lease


def update_lease(user, workspace, lease_id, changes):
    """Update contractual Lease fields only before the contract is effective."""
    _require_active_member(user, workspace)
    changes = dict(changes or {})
    unsupported = set(changes) - MUTABLE_FIELDS
    if unsupported:
        raise ValidationError(f"Unsupported lease fields: {sorted(unsupported)}")
    if not changes:
        raise ValidationError("No lease changes supplied")

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        if lease.status in IMMUTABLE_CONTRACT_STATUSES:
            raise ValidationError("Contractual lease facts are immutable after activation")

        for field, value in changes.items():
            if field in {"rent_amount", "security_deposit"}:
                value = _decimal(value, field.replace("_", " ").title())
            setattr(lease, field, value)
        lease.updated_by = user
        lease.save()
        return lease


def transition_lease(user, workspace, lease_id, target_status):
    """Apply non-terminal Lease lifecycle transitions atomically and record their event."""
    _require_active_member(user, workspace)
    if target_status not in Lease.VALID_STATUSES:
        raise ValidationError("Invalid lease status")
    if target_status in {Lease.STATUS_EXPIRED, Lease.STATUS_TERMINATED}:
        raise ValidationError(
            "Terminal lease transitions must use their dedicated lifecycle service"
        )

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        if lease.status == target_status:
            return lease

        previous_status = lease.status
        allowed = ALLOWED_TRANSITIONS.get(previous_status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Invalid lease transition: {previous_status} -> {target_status}"
            )

        from django.utils import timezone
        now = timezone.now()
        if target_status == Lease.STATUS_ACTIVE:
            lease.activated_at = now
            lease.status = target_status
            lease.updated_by = user
            lease.save()
            _ensure_active_contract_version(lease)
        else:
            lease.status = target_status
            lease.updated_by = user
            lease.save()

        append_lifecycle_event(
            lease=lease,
            event_type=STATUS_EVENT_TYPES[target_status],
            actor=user,
            occurred_at=now,
            effective_date=now.date(),
            metadata={
                "from_status": previous_status,
                "to_status": target_status,
            },
            event_key=STATUS_EVENT_TYPES[target_status],
        )
        return lease
