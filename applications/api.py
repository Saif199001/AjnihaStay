from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
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


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


def _application_payload(application):
    return {"data": ApplicationSerializer(application).data}


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def applicant_create_api(request):
    serializer = ApplicantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        applicant = create_applicant(request.workspace, serializer.validated_data, request.user)
        return Response({"message": "Applicant created", "data": ApplicantSerializer(applicant).data}, status=201)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def applicant_list_api(request):
    return Response({"data": ApplicantSerializer(list_applicants(request.workspace), many=True).data})


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
        return Response({"data": ApplicationSerializer(applications, many=True).data})
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
        return Response({"message": f"Application {transition}d" if transition in {"approve", "reject"} else f"Application {transition}ed", **_application_payload(application)})
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_submit_api(request, application_id):
    return _transition_response(request, "submit", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_review_api(request, application_id):
    return _transition_response(request, "review", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_approve_api(request, application_id):
    return _transition_response(request, "approve", application_id)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_reject_api(request, application_id):
    reason = request.data.get("reason", "")
    return _transition_response(request, "reject", application_id, reason)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def application_withdraw_api(request, application_id):
    reason = request.data.get("reason", "")
    return _transition_response(request, "withdraw", application_id, reason)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def application_history_api(request, application_id):
    try:
        history = get_application_history(request.workspace, application_id)
        return Response({"data": ApplicationEventSerializer(history, many=True).data})
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404)
