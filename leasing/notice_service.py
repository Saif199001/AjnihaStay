from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.authorization import require_mutation_permission

from .lease_service import _get_locked_lease
from .lifecycle_event_service import append_lifecycle_event
from .lifecycle_models import LeaseLifecycleEvent, LeaseNotice


NOTICE_TRANSITIONS = {
    LeaseNotice.STATUS_DRAFT: {LeaseNotice.STATUS_ISSUED, LeaseNotice.STATUS_WITHDRAWN},
    LeaseNotice.STATUS_ISSUED: {LeaseNotice.STATUS_EFFECTIVE, LeaseNotice.STATUS_WITHDRAWN},
    LeaseNotice.STATUS_EFFECTIVE: {LeaseNotice.STATUS_COMPLETED},
    LeaseNotice.STATUS_WITHDRAWN: set(),
    LeaseNotice.STATUS_COMPLETED: set(),
}


def _get_locked_notice(notice_id, workspace):
    try:
        return (
            LeaseNotice.objects.select_for_update()
            .select_related("lease")
            .get(id=notice_id, workspace=workspace)
        )
    except (LeaseNotice.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Notice not found")


def create_notice(user, workspace, lease_id, *, notice_date, effective_date, notice_type, reason):
    require_mutation_permission(user, workspace)
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError("Notice reason is required")
    if notice_type not in dict(LeaseNotice.TYPE_CHOICES):
        raise ValidationError("Invalid notice type")
    today = timezone.localdate()
    if notice_date > today:
        raise ValidationError("Notice date cannot be in the future")
    if effective_date < notice_date:
        raise ValidationError("Notice effective date cannot be before notice date")

    with transaction.atomic():
        lease = _get_locked_lease(lease_id, workspace)
        if lease.status not in {lease.STATUS_ACTIVE, lease.STATUS_EXPIRED}:
            raise ValidationError("Notices can only be created for active or expired leases")
        notice = LeaseNotice(
            workspace=workspace,
            lease=lease,
            notice_date=notice_date,
            effective_date=effective_date,
            notice_type=notice_type,
            reason=reason,
            status=LeaseNotice.STATUS_DRAFT,
            created_by=user,
        )
        notice.save()
        append_lifecycle_event(
            lease=lease,
            event_type=LeaseLifecycleEvent.EVENT_NOTICE,
            actor=user,
            occurred_at=notice.created_at,
            effective_date=notice.effective_date,
            metadata={"notice_id": notice.id, "status": notice.status, "notice_type": notice.notice_type},
            event_key=f"notice:{notice.id}:created",
        )
        return notice


def transition_notice(user, workspace, notice_id, target_status):
    require_mutation_permission(user, workspace)
    if target_status not in dict(LeaseNotice.STATUS_CHOICES):
        raise ValidationError("Invalid notice status")

    with transaction.atomic():
        notice = _get_locked_notice(notice_id, workspace)
        if notice.status == target_status:
            return notice
        if target_status not in NOTICE_TRANSITIONS.get(notice.status, set()):
            raise ValidationError(f"Invalid notice transition: {notice.status} -> {target_status}")

        today = timezone.localdate()
        if target_status == LeaseNotice.STATUS_EFFECTIVE and notice.effective_date > today:
            raise ValidationError("Notice cannot become effective before its effective date")
        if target_status == LeaseNotice.STATUS_COMPLETED and notice.effective_date > today:
            raise ValidationError("Notice cannot be completed before its effective date")

        previous_status = notice.status
        notice.status = target_status
        notice.save()
        append_lifecycle_event(
            lease=notice.lease,
            event_type=LeaseLifecycleEvent.EVENT_NOTICE,
            actor=user,
            occurred_at=timezone.now(),
            effective_date=notice.effective_date,
            metadata={
                "notice_id": notice.id,
                "from_status": previous_status,
                "to_status": target_status,
                "notice_type": notice.notice_type,
            },
            event_key=f"notice:{notice.id}:{target_status}",
        )
        return notice


def issue_notice(user, workspace, notice_id):
    return transition_notice(user, workspace, notice_id, LeaseNotice.STATUS_ISSUED)


def withdraw_notice(user, workspace, notice_id):
    return transition_notice(user, workspace, notice_id, LeaseNotice.STATUS_WITHDRAWN)


def make_notice_effective(user, workspace, notice_id):
    return transition_notice(user, workspace, notice_id, LeaseNotice.STATUS_EFFECTIVE)


def complete_notice(user, workspace, notice_id):
    return transition_notice(user, workspace, notice_id, LeaseNotice.STATUS_COMPLETED)
