from django.utils import timezone

from .lifecycle_models import LeaseLifecycleEvent


def append_lifecycle_event(
    *,
    lease,
    event_type,
    actor=None,
    occurred_at=None,
    effective_date=None,
    metadata=None,
    event_key=None,
):
    """Append one immutable, workspace-scoped lifecycle event idempotently.

    Canonical lifecycle services call this inside their surrounding transaction.
    The database uniqueness constraint protects the event key from duplicate
    writes when the same transition is retried.
    """
    if event_type not in dict(LeaseLifecycleEvent.EVENT_CHOICES):
        raise ValueError(f"Unsupported lease lifecycle event: {event_type}")

    occurred_at = occurred_at or timezone.now()
    defaults = {
        "workspace": lease.workspace,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "effective_date": effective_date,
        "actor": actor,
        "metadata": dict(metadata or {}),
    }

    if event_key is None:
        event_key = event_type

    event, _ = LeaseLifecycleEvent.objects.get_or_create(
        lease=lease,
        event_key=event_key,
        defaults=defaults,
    )
    return event
