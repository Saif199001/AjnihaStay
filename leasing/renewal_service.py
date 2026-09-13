from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.authorization import require_mutation_permission

from .lifecycle_models import LeaseRenewal
from .models import Lease


def _require_manager(user, workspace):
    require_mutation_permission(user, workspace)


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


def _get_locked_source_lease(lease_id, workspace):
    try:
        return Lease.objects.select_for_update().get(id=lease_id, workspace=workspace)
    except (Lease.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Lease not found")


def _overlaps(start_date, end_date, periods):
    return any(start_date <= existing_end and end_date >= existing_start for existing_start, existing_end in periods)


def create_renewal(user, workspace, source_lease_id, data):
    """Create a draft renewal through the canonical P1.5 mutation boundary."""
    _require_manager(user, workspace)
    data = dict(data or {})

    with transaction.atomic():
        source_lease = _get_locked_source_lease(source_lease_id, workspace)
        if source_lease.status in {Lease.STATUS_DRAFT, Lease.STATUS_PENDING_SIGNATURE, Lease.STATUS_CANCELLED}:
            raise ValidationError("Only active or expired leases can be renewed")

        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if not start_date or not end_date:
            raise ValidationError("Renewal start and end dates are required")
        if end_date < start_date:
            raise ValidationError("Renewal end date cannot be before start date")

        renewal_number = data.get("renewal_number")
        if renewal_number is None:
            latest = (
                LeaseRenewal.objects.filter(source_lease=source_lease)
                .order_by("-renewal_number")
                .values_list("renewal_number", flat=True)
                .first()
            )
            renewal_number = (latest or 0) + 1
        if not isinstance(renewal_number, int) or isinstance(renewal_number, bool) or renewal_number < 1:
            raise ValidationError("Renewal number must be a positive integer")

        periods = [(source_lease.start_date, source_lease.end_date)]
        periods.extend(
            LeaseRenewal.objects.filter(source_lease=source_lease)
            .values_list("start_date", "end_date")
        )
        if _overlaps(start_date, end_date, periods):
            raise ValidationError("Renewal contractual period overlaps an existing lease period")

        allowed = {
            "renewal_number",
            "start_date",
            "end_date",
            "rent_amount",
            "security_deposit",
            "notice_period_days",
            "terms",
            "agreement_reference",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError(f"Unsupported renewal fields: {sorted(unknown)}")

        renewal = LeaseRenewal(
            workspace=workspace,
            source_lease=source_lease,
            renewal_number=renewal_number,
            start_date=start_date,
            end_date=end_date,
            rent_amount=_decimal(data.get("rent_amount", source_lease.rent_amount), "Rent amount"),
            security_deposit=_decimal(
                data.get("security_deposit", source_lease.security_deposit),
                "Security deposit",
            ),
            notice_period_days=data.get("notice_period_days", source_lease.notice_period_days),
            terms=data.get("terms") if data.get("terms") is not None else dict(source_lease.terms or {}),
            agreement_reference=data.get("agreement_reference", source_lease.agreement_reference),
            created_by=user,
        )
        renewal.save()
        return renewal


def confirm_renewal(user, workspace, renewal_id):
    """Confirm a draft renewal atomically; confirmed renewals are immutable."""
    _require_manager(user, workspace)

    with transaction.atomic():
        try:
            renewal = (
                LeaseRenewal.objects.select_for_update()
                .select_related("source_lease")
                .get(id=renewal_id, workspace=workspace)
            )
        except (LeaseRenewal.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Renewal not found")

        if renewal.status == LeaseRenewal.STATUS_CONFIRMED:
            return renewal
        if renewal.status != LeaseRenewal.STATUS_DRAFT:
            raise ValidationError("Only draft renewals can be confirmed")

        source_lease = _get_locked_source_lease(renewal.source_lease_id, workspace)
        if source_lease.status in {Lease.STATUS_DRAFT, Lease.STATUS_PENDING_SIGNATURE, Lease.STATUS_CANCELLED}:
            raise ValidationError("Only active or expired leases can be renewed")

        renewal.status = LeaseRenewal.STATUS_CONFIRMED
        renewal.confirmed_at = timezone.now()
        renewal.save()
        return renewal


def cancel_renewal(user, workspace, renewal_id):
    """Cancel a draft renewal atomically."""
    _require_manager(user, workspace)

    with transaction.atomic():
        try:
            renewal = LeaseRenewal.objects.select_for_update().get(id=renewal_id, workspace=workspace)
        except (LeaseRenewal.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Renewal not found")

        if renewal.status == LeaseRenewal.STATUS_CANCELLED:
            return renewal
        if renewal.status != LeaseRenewal.STATUS_DRAFT:
            raise ValidationError("Only draft renewals can be cancelled")

        renewal.status = LeaseRenewal.STATUS_CANCELLED
        renewal.cancelled_at = timezone.now()
        renewal.save()
        return renewal
