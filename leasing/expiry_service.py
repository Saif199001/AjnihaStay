from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.authorization import require_mutation_permission

from .lease_service import _ensure_active_contract_version, _get_locked_lease
from .lifecycle_event_service import append_lifecycle_event
from .lifecycle_models import LeaseLifecycleEvent
from .models import Lease


def expire_lease(user, workspace, lease_id, *, effective_date=None):
    """Expire an active Lease at the end of its current contract version.

    Expiry is a lifecycle operation only: it changes Lease state and records
    immutable lifecycle history. It never moves out the Occupancy or mutates
    financial truth.
    """
    require_mutation_permission(user, workspace)

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)

        if lease.status == Lease.STATUS_EXPIRED:
            event = LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
            ).first()
            if event and (effective_date is None or effective_date == event.effective_date):
                return lease
            raise ValidationError("Lease is already expired with immutable expiry details")

        if lease.status != Lease.STATUS_ACTIVE:
            raise ValidationError(
                f"Only active leases can expire; current status is {lease.status}"
            )

        contract_version = _ensure_active_contract_version(lease)
        latest_version = (
            type(contract_version).objects.select_for_update()
            .filter(lease=lease)
            .order_by("-version_number")
            .first()
        )
        if latest_version is None:
            raise ValidationError("Active lease contract version not found")

        expiry_date = latest_version.end_date
        if effective_date is not None and effective_date != expiry_date:
            raise ValidationError(
                "Lease expiry effective date must match the active contract end date"
            )

        now = timezone.now()
        previous_status = lease.status
        lease.status = Lease.STATUS_EXPIRED
        lease.updated_by = user
        lease.save()

        append_lifecycle_event(
            lease=lease,
            event_type=LeaseLifecycleEvent.EVENT_EXPIRED,
            actor=user,
            occurred_at=now,
            effective_date=expiry_date,
            metadata={
                "from_status": previous_status,
                "to_status": Lease.STATUS_EXPIRED,
                "contract_version_id": latest_version.id,
                "contract_version_number": latest_version.version_number,
            },
            event_key=LeaseLifecycleEvent.EVENT_EXPIRED,
        )
        return lease
