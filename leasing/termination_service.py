from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.authorization import require_mutation_permission

from .lease_service import _ensure_active_contract_version, _get_locked_lease
from .lifecycle_event_service import append_lifecycle_event
from .lifecycle_models import LeaseLifecycleEvent
from .models import Lease


MAX_TERMINATION_REASON_LENGTH = 500


def terminate_lease(user, workspace, lease_id, *, reason, effective_date=None):
    """Terminate an active Lease through the canonical lifecycle boundary.

    Termination is an explicit lifecycle operation and is intentionally
    independent from expiry. It records the reason and effective date in the
    immutable lifecycle event while leaving Occupancy and financial truth
    untouched.
    """
    require_mutation_permission(user, workspace)

    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ValidationError("Termination reason is required")
    if len(normalized_reason) > MAX_TERMINATION_REASON_LENGTH:
        raise ValidationError(
            f"Termination reason cannot exceed {MAX_TERMINATION_REASON_LENGTH} characters"
        )

    requested_date = effective_date or timezone.localdate()
    today = timezone.localdate()
    if requested_date < today and requested_date < today:
        # Past effective dates are intentionally rejected for the immediate
        # state transition; historical corrections require a separate policy.
        raise ValidationError("Termination effective date cannot be in the past")
    if requested_date > today:
        raise ValidationError("Termination effective date cannot be in the future")

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)

        if lease.status == Lease.STATUS_TERMINATED:
            event = LeaseLifecycleEvent.objects.filter(
                lease=lease,
                event_key=LeaseLifecycleEvent.EVENT_TERMINATED,
            ).first()
            if event and (
                event.effective_date != requested_date
                or event.metadata.get("reason") != normalized_reason
            ):
                raise ValidationError("Lease is already terminated with immutable termination details")
            return lease

        if lease.status != Lease.STATUS_ACTIVE:
            raise ValidationError(
                f"Only active leases can terminate; current status is {lease.status}"
            )

        if requested_date < lease.start_date:
            raise ValidationError("Termination effective date cannot be before lease start date")

        contract_version = _ensure_active_contract_version(lease)
        latest_version = (
            type(contract_version).objects.select_for_update()
            .filter(lease=lease)
            .order_by("-version_number")
            .first()
        )
        if latest_version is None:
            raise ValidationError("Active lease contract version not found")

        now = timezone.now()
        previous_status = lease.status
        lease.status = Lease.STATUS_TERMINATED
        lease.terminated_at = now
        lease.updated_by = user
        lease.save()

        append_lifecycle_event(
            lease=lease,
            event_type=LeaseLifecycleEvent.EVENT_TERMINATED,
            actor=user,
            occurred_at=now,
            effective_date=requested_date,
            metadata={
                "from_status": previous_status,
                "to_status": Lease.STATUS_TERMINATED,
                "reason": normalized_reason,
                "contract_version_id": latest_version.id,
                "contract_version_number": latest_version.version_number,
            },
            event_key=LeaseLifecycleEvent.EVENT_TERMINATED,
        )
        return lease
