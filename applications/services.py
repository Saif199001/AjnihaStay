from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Applicant, Application, ApplicationEvent


_ACTIVE_STATUSES = Application.ACTIVE_STATUSES


def _clean_text(value):
    return (value or "").strip()


def _require_actor(actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise ValidationError("Authenticated actor required")
    if hasattr(actor, "is_active") and not actor.is_active:
        raise ValidationError("Actor account is inactive")
    return actor


def _get_applicant_for_workspace(workspace, applicant_value):
    applicant_id = getattr(applicant_value, "id", applicant_value)
    try:
        return Applicant.objects.get(id=applicant_id, workspace=workspace)
    except (Applicant.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Applicant not found")


def _get_application_for_workspace(workspace, application_id, lock=False):
    queryset = Application.objects.filter(id=application_id, workspace=workspace)
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.select_related("applicant", "property", "unit", "subunit").get()
    except (Application.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Application not found")


def _validate_inventory(workspace, property_value, unit_value=None, subunit_value=None):
    from properties.models import Property
    from unit.models import SubUnit, Unit

    property_id = getattr(property_value, "id", property_value)
    try:
        property_obj = Property.objects.get(id=property_id, workspace=workspace)
    except (Property.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Property not found")

    unit_obj = None
    if unit_value not in (None, ""):
        unit_id = getattr(unit_value, "id", unit_value)
        try:
            unit_obj = Unit.objects.select_related("property").get(
                id=unit_id,
                property=property_obj,
            )
        except (Unit.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Unit not found")

    subunit_obj = None
    if subunit_value not in (None, ""):
        subunit_id = getattr(subunit_value, "id", subunit_value)
        if unit_obj is None:
            raise ValidationError("SubUnit requires a Unit")
        try:
            subunit_obj = SubUnit.objects.select_related("unit", "unit__property").get(
                id=subunit_id,
                unit=unit_obj,
            )
        except (SubUnit.DoesNotExist, TypeError, ValueError):
            raise ValidationError("SubUnit not found")

    return property_obj, unit_obj, subunit_obj


def _validate_dates(check_in, check_out):
    if check_in and check_out and check_out < check_in:
        raise ValidationError("Requested check-out date cannot be before check-in date")


def create_applicant(workspace, data, actor=None):
    if actor is not None:
        _require_actor(actor)

    full_name = _clean_text(data.get("full_name"))
    phone = _clean_text(data.get("phone"))
    email = _clean_text(data.get("email")) or None
    address = _clean_text(data.get("address"))

    if not full_name:
        raise ValidationError("Full name required")
    if not phone:
        raise ValidationError("Phone number required")

    with transaction.atomic():
        # Applicant identity is workspace-local. Phone/email are matching
        # signals, never global identity keys. Ambiguous matches are rejected.
        phone_matches = list(
            Applicant.objects.select_for_update().filter(workspace=workspace, phone=phone)
        )
        email_matches = []
        if email:
            email_matches = list(
                Applicant.objects.select_for_update()
                .filter(workspace=workspace, email__iexact=email)
            )

        matched_ids = {obj.id for obj in phone_matches + email_matches}
        if len(matched_ids) > 1:
            raise ValidationError("Applicant identity match is ambiguous")
        if matched_ids:
            return Applicant.objects.get(
                id=next(iter(matched_ids)), workspace=workspace
            )

        return Applicant.objects.create(
            workspace=workspace,
            full_name=full_name,
            phone=phone,
            email=email,
            address=address,
        )


def get_applicant(workspace, applicant_id):
    try:
        return Applicant.objects.get(id=applicant_id, workspace=workspace)
    except (Applicant.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Applicant not found")


def list_applicants(workspace):
    return Applicant.objects.filter(workspace=workspace).order_by("id")


def create_application(workspace, data, actor):
    actor = _require_actor(actor)
    with transaction.atomic():
        applicant = _get_applicant_for_workspace(workspace, data.get("applicant"))
        property_obj, unit_obj, subunit_obj = _validate_inventory(
            workspace,
            data.get("property"),
            data.get("unit"),
            data.get("subunit"),
        )
        check_in = data.get("requested_check_in_date")
        check_out = data.get("requested_check_out_date")
        _validate_dates(check_in, check_out)

        # Lock the applicant aggregate before checking the active-application
        # scope. The partial unique constraint remains the database backstop.
        applicant = Applicant.objects.select_for_update().get(
            id=applicant.id, workspace=workspace
        )
        if Application.objects.filter(
            workspace=workspace,
            applicant=applicant,
            property=property_obj,
            status__in=_ACTIVE_STATUSES,
        ).exists():
            raise ValidationError(
                "An active application already exists for this applicant and property"
            )

        application = Application(
            workspace=workspace,
            applicant=applicant,
            property=property_obj,
            unit=unit_obj,
            subunit=subunit_obj,
            requested_check_in_date=check_in,
            requested_check_out_date=check_out,
            status=Application.STATUS_DRAFT,
            created_by=actor,
            updated_by=actor,
        )
        application.full_clean()
        try:
            application.save()
        except IntegrityError:
            raise ValidationError(
                "An active application already exists for this applicant and property"
            )
        return application


def get_application(workspace, application_id):
    return _get_application_for_workspace(workspace, application_id)


def list_applications(workspace, status=None, applicant_id=None, property_id=None):
    queryset = Application.objects.filter(workspace=workspace)
    if status:
        if status not in dict(Application.STATUS_CHOICES):
            raise ValidationError("Invalid application status")
        queryset = queryset.filter(status=status)
    if applicant_id not in (None, ""):
        queryset = queryset.filter(applicant_id=applicant_id)
    if property_id not in (None, ""):
        queryset = queryset.filter(property_id=property_id)
    return queryset.select_related(
        "applicant", "property", "unit", "subunit"
    ).order_by("-created_at", "-id")


def _transition(
    workspace,
    application_id,
    actor,
    *,
    target_status,
    reason="",
    event_key=None,
):
    actor = _require_actor(actor)
    reason = _clean_text(reason)

    with transaction.atomic():
        application = _get_application_for_workspace(workspace, application_id, lock=True)
        current_status = application.status

        allowed = {
            Application.STATUS_DRAFT: {Application.STATUS_SUBMITTED},
            Application.STATUS_SUBMITTED: {
                Application.STATUS_UNDER_REVIEW,
                Application.STATUS_WITHDRAWN,
            },
            Application.STATUS_UNDER_REVIEW: {
                Application.STATUS_APPROVED,
                Application.STATUS_REJECTED,
                Application.STATUS_WITHDRAWN,
            },
        }

        # Repeating the same already-completed action is deterministic and does
        # not append a duplicate logical history event.
        if current_status == target_status:
            return application, False

        if target_status not in allowed.get(current_status, set()):
            raise ValidationError(
                f"Invalid application transition: {current_status} -> {target_status}"
            )

        if target_status == Application.STATUS_REJECTED and not reason:
            raise ValidationError("Rejection reason required")

        now = timezone.now()
        application.status = target_status
        application.updated_by = actor

        if target_status == Application.STATUS_SUBMITTED:
            application.submitted_at = now
            application.rejection_reason = ""
            application.withdrawal_reason = ""
        elif target_status == Application.STATUS_UNDER_REVIEW:
            application.reviewed_at = now
        elif target_status == Application.STATUS_APPROVED:
            application.decided_at = now
            application.rejection_reason = ""
            application.withdrawal_reason = ""
        elif target_status == Application.STATUS_REJECTED:
            application.decided_at = now
            application.rejection_reason = reason
        elif target_status == Application.STATUS_WITHDRAWN:
            application.withdrawal_reason = reason

        application._allow_lifecycle_mutation = True
        application.save(
            update_fields=[
                "status",
                "submitted_at",
                "reviewed_at",
                "decided_at",
                "rejection_reason",
                "withdrawal_reason",
                "updated_by",
                "updated_at",
            ]
        )

        if event_key is None:
            event_key = f"status:{current_status}:{target_status}"

        # Isolate the uniqueness failure in a savepoint so the outer
        # transaction remains usable for deterministic retry handling.
        try:
            with transaction.atomic():
                ApplicationEvent.append(
                    workspace=workspace,
                    application=application,
                    applicant=application.applicant,
                    from_status=current_status,
                    to_status=target_status,
                    actor=actor,
                    occurred_at=now,
                    reason=reason,
                    metadata={},
                    event_key=event_key,
                )
        except IntegrityError:
            existing = ApplicationEvent.objects.filter(
                application=application,
                event_key=event_key,
            ).first()
            if existing:
                return application, False
            raise

        return application, True


def submit_application(workspace, application_id, actor):
    return _transition(
        workspace,
        application_id,
        actor,
        target_status=Application.STATUS_SUBMITTED,
    )[0]


def review_application(workspace, application_id, actor):
    return _transition(
        workspace,
        application_id,
        actor,
        target_status=Application.STATUS_UNDER_REVIEW,
    )[0]


def approve_application(workspace, application_id, actor):
    # Approval is deliberately isolated: it changes Application workflow state
    # only. It never creates Tenant, Occupancy, Lease, Invoice, Charge or Payment.
    return _transition(
        workspace,
        application_id,
        actor,
        target_status=Application.STATUS_APPROVED,
    )[0]


def reject_application(workspace, application_id, actor, reason):
    return _transition(
        workspace,
        application_id,
        actor,
        target_status=Application.STATUS_REJECTED,
        reason=reason,
    )[0]


def withdraw_application(workspace, application_id, actor, reason=""):
    return _transition(
        workspace,
        application_id,
        actor,
        target_status=Application.STATUS_WITHDRAWN,
        reason=reason,
    )[0]


def get_application_history(workspace, application_id):
    application = _get_application_for_workspace(workspace, application_id)
    return ApplicationEvent.objects.filter(
        workspace=workspace,
        application=application,
    ).select_related("actor", "applicant").order_by("occurred_at", "id")
