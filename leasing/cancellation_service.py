from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.authorization import require_mutation_permission

from .lease_service import _get_locked_lease
from .lifecycle_event_service import append_lifecycle_event
from .lifecycle_models import LeaseLifecycleEvent
from .models import Lease

MAX_CANCELLATION_REASON_LENGTH = 500


def cancel_lease(user, workspace, lease_id, *, reason, effective_date=None):
    require_mutation_permission(user, workspace)
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ValidationError("Cancellation reason is required")
    if len(normalized_reason) > MAX_CANCELLATION_REASON_LENGTH:
        raise ValidationError("Cancellation reason is too long")
    effective_date = effective_date or timezone.localdate()
    if effective_date > timezone.localdate():
        raise ValidationError("Cancellation effective date cannot be in the future")
    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        if lease.status == Lease.STATUS_CANCELLED:
            event = LeaseLifecycleEvent.objects.filter(lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED).first()
            if event:
                existing_reason = (event.metadata or {}).get("reason")
                if existing_reason == normalized_reason and event.effective_date == effective_date:
                    return lease
            raise ValidationError("Lease is already cancelled")
        if lease.status not in {Lease.STATUS_DRAFT, Lease.STATUS_PENDING_SIGNATURE}:
            raise ValidationError("Only draft or pending-signature leases can be cancelled")
        now = timezone.now()
        previous_status = lease.status
        lease.status = Lease.STATUS_CANCELLED
        lease.cancelled_at = now
        lease.updated_by = user
        lease.save(_allow_lifecycle_mutation=True)
        append_lifecycle_event(lease=lease, event_type=LeaseLifecycleEvent.EVENT_CANCELLED, actor=user,
                               occurred_at=now, effective_date=effective_date,
                               metadata={"from_status": previous_status, "to_status": Lease.STATUS_CANCELLED,
                                         "reason": normalized_reason},
                               event_key=LeaseLifecycleEvent.EVENT_CANCELLED)
        return lease
