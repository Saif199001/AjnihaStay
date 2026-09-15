from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission
from .serializers import ApplicantSerializer, ApplicationEventSerializer, ApplicationSerializer
from .services import (
    approve_application,
    create_applicant,
    create_application,
    get_application,
    get_application_history,
    get_applicant,
    list_applications,
    list_applicants,
    reject_application,
    review_application,
    submit_application,
    withdraw_application,
)


class ApplicationApiPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


def _application_payload(application):
    return {"data": ApplicationSerializer(application).data}


def _paginate_response(request, queryset, serializer_class):
    paginator = ApplicationApiPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True)
    return Response({
        "data": serializer.data,
        "pagination": {
            "count": paginator.page.paginator.count,
            "page": paginator.page.number,
            "page_size": paginator.get_page_size(request),
            "num_pages": paginator.page.paginator.num_pages,
        },
    })


def _validate_transition_payload(request, *, allow_reason=False):
    allowed = {"reason"} if allow_reason else set()
    unknown = sorted(set(request.data.keys()) - allowed)
    if unknown:
        return Response(
            {"error": f"Unknown field(s): {', '.join(unknown)}"},
            status=400,
        )
    return None


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def applicant_create_api(request):
    serializer = ApplicantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        applicant = create_applicant(request.workspace, serializer.validated_data, request.user)
        return Response({"message": "Applicant saved", "data": ApplicantSerializer(applicant).data}, status=201)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def applicant_list_api(request):
    return _paginate_response(request, list_applicants(request.workspace), ApplicantSerializer)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def applicant_detail_api(request, applicant_id):
    try:
        applicant = get_applicant(request.workspace, applicant_id)
        return Response({"data": ApplicantSerializer(applicant).data})
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_create_api(request):
    serializer = ApplicationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        application = create_application(request.workspace, serializer.validated_data, request.user)
        return Response({"message": "Application created", **_application_payload(application)}, status=201)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def application_list_api(request):
    try:
        applications = list_applications(
            request.workspace,
            status=request.GET.get("status"),
            applicant_id=request.GET.get("applicant"),
            property_id=request.GET.get("property"),
        )
        return _paginate_response(request, applications, ApplicationSerializer)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def application_detail_api(request, application_id):
    try:
        application = get_application(request.workspace, application_id)
        return Response(_application_payload(application))
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)


def _transition_response(request, transition, application_id, reason=None):
    messages = {
        "submit": "Application submitted",
        "review": "Application moved to review",
        "approve": "Application approved",
        "reject": "Application rejected",
        "withdraw": "Application withdrawn",
    }
    try:
        if transition == "submit":
            application = submit_application(request.workspace, application_id, request.user)
        elif transition == "review":
            application = review_application(request.workspace, application_id, request.user)
        elif transition == "approve":
            application = approve_application(request.workspace, application_id, request.user)
        elif transition == "reject":
            application = reject_application(request.workspace, application_id, request.user, reason or "")
        else:
            application = withdraw_application(request.workspace, application_id, request.user, reason or "")
        return Response({"message": messages[transition], **_application_payload(application)})
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_submit_api(request, application_id):
    error = _validate_transition_payload(request)
    if error:
        return error
    return _transition_response(request, "submit", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_review_api(request, application_id):
    error = _validate_transition_payload(request)
    if error:
        return error
    return _transition_response(request, "review", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_approve_api(request, application_id):
    error = _validate_transition_payload(request)
    if error:
        return error
    return _transition_response(request, "approve", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_reject_api(request, application_id):
    error = _validate_transition_payload(request, allow_reason=True)
    if error:
        return error
    return _transition_response(request, "reject", application_id, request.data.get("reason", ""))


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_withdraw_api(request, application_id):
    error = _validate_transition_payload(request, allow_reason=True)
    if error:
        return error
    return _transition_response(request, "withdraw", application_id, request.data.get("reason", ""))


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def application_history_api(request, application_id):
    try:
        history = get_application_history(request.workspace, application_id)
        return _paginate_response(request, history, ApplicationEventSerializer)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
