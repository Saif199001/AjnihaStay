from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission

from .cancellation_service import cancel_lease
from .expiry_service import expire_lease
from .lease_service import create_lease, transition_lease, update_lease
from .lifecycle_models import LeaseNotice
from .models import Lease
from .notice_service import create_notice, transition_notice
from .serializers import LeaseLifecycleActionSerializer, LeaseNoticeSerializer, LeaseNoticeTransitionSerializer, LeaseSerializer, LeaseTransitionSerializer
from .termination_service import terminate_lease


def _validation_message(exc):
    return exc.messages[0] if exc.messages else str(exc)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def lease_list_api(request):
    leases = Lease.objects.filter(workspace=request.workspace).select_related("occupancy__tenant")
    return Response({"data": LeaseSerializer(leases, many=True).data})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def lease_detail_api(request, lease_id):
    try:
        lease = Lease.objects.select_related("occupancy__tenant").get(id=lease_id, workspace=request.workspace)
    except Lease.DoesNotExist:
        return Response({"error": "Lease not found"}, status=404)
    return Response({"data": LeaseSerializer(lease).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_create_api(request):
    serializer = LeaseSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        lease = create_lease(request.user, request.workspace, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Lease created", "data": LeaseSerializer(lease).data}, status=201)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_update_api(request, lease_id):
    serializer = LeaseSerializer(data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        lease = update_lease(request.user, request.workspace, lease_id, serializer.validated_data)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Lease updated", "data": LeaseSerializer(lease).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_transition_api(request, lease_id):
    serializer = LeaseTransitionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        lease = transition_lease(request.user, request.workspace, lease_id, serializer.validated_data["status"])
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Lease status updated", "data": LeaseSerializer(lease).data})


def _lease_action_api(request, lease_id, action):
    serializer = LeaseLifecycleActionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    data = serializer.validated_data
    try:
        if action == "expire":
            lease = expire_lease(request.user, request.workspace, lease_id, effective_date=data.get("effective_date"))
            message = "Lease expired"
        elif action == "terminate":
            if "reason" not in data:
                return Response({"error": "Termination reason is required"}, status=400)
            lease = terminate_lease(request.user, request.workspace, lease_id, reason=data["reason"], effective_date=data.get("effective_date"))
            message = "Lease terminated"
        else:
            if "reason" not in data:
                return Response({"error": "Cancellation reason is required"}, status=400)
            lease = cancel_lease(request.user, request.workspace, lease_id, reason=data["reason"], effective_date=data.get("effective_date"))
            message = "Lease cancelled"
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": message, "data": LeaseSerializer(lease).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_expire_api(request, lease_id):
    return _lease_action_api(request, lease_id, "expire")


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_terminate_api(request, lease_id):
    return _lease_action_api(request, lease_id, "terminate")


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_cancel_api(request, lease_id):
    return _lease_action_api(request, lease_id, "cancel")


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_notice_create_api(request, lease_id):
    serializer = LeaseNoticeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    data = serializer.validated_data
    try:
        notice = create_notice(request.user, request.workspace, lease_id, notice_date=data["notice_date"], effective_date=data["effective_date"], notice_type=data["notice_type"], reason=data["reason"])
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Notice created", "data": LeaseNoticeSerializer(notice).data}, status=201)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def lease_notice_transition_api(request, notice_id):
    serializer = LeaseNoticeTransitionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        notice = transition_notice(request.user, request.workspace, notice_id, serializer.validated_data["status"])
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    return Response({"message": "Notice status updated", "data": LeaseNoticeSerializer(notice).data})
