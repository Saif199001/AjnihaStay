from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from workspaces.permissions import WorkspaceManagerPermission, WorkspaceStaffPermission

from .models import AgreementLink, KycDocument, KycDocumentEvent, KycProfile, KycVerificationEvent
from .serializers import (
    AgreementLinkCreateSerializer,
    AgreementLinkSerializer,
    KycDocumentEventSerializer,
    KycDocumentReviewSerializer,
    KycDocumentSerializer,
    KycDocumentUploadSerializer,
    KycProfileSerializer,
    KycRejectSerializer,
    KycVerificationEventSerializer,
)
from .services import (
    create_agreement_link,
    get_or_create_profile,
    reject_kyc,
    review_document,
    submit_kyc,
    upload_document,
    verify_kyc,
)
from .storage import CloudinaryPrivateDocumentStorage, PrivateStorageError


def _error(exc):
    messages = getattr(exc, "messages", None)
    return messages[0] if messages else str(exc)


def _tenant_or_404(tenant_id, workspace):
    from tenant.models import Tenant
    try:
        return Tenant.objects.get(id=tenant_id, workspace=workspace)
    except (Tenant.DoesNotExist, TypeError, ValueError):
        return None


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def kyc_detail_api(request, tenant_id):
    tenant = _tenant_or_404(tenant_id, request.workspace)
    if tenant is None:
        return Response({"error": "Tenant not found"}, status=404)
    profile = get_or_create_profile(request.user, request.workspace, tenant.id)
    return Response({"data": KycProfileSerializer(profile).data})


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def kyc_submit_api(request, tenant_id):
    try:
        profile = submit_kyc(request.user, request.workspace, tenant_id)
        return Response({"data": KycProfileSerializer(profile).data})
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def kyc_verify_api(request, tenant_id):
    try:
        profile = verify_kyc(request.user, request.workspace, tenant_id)
        return Response({"data": KycProfileSerializer(profile).data})
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def kyc_reject_api(request, tenant_id):
    serializer = KycRejectSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        profile = reject_kyc(request.user, request.workspace, tenant_id, reason=serializer.validated_data["reason"])
        return Response({"data": KycProfileSerializer(profile).data})
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def kyc_history_api(request, tenant_id):
    tenant = _tenant_or_404(tenant_id, request.workspace)
    if tenant is None:
        return Response({"error": "Tenant not found"}, status=404)
    events = KycVerificationEvent.objects.filter(tenant=tenant, workspace=request.workspace).order_by("occurred_at", "id")
    return Response({"data": KycVerificationEventSerializer(events, many=True).data})


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([WorkspaceStaffPermission])
def kyc_documents_api(request, tenant_id):
    tenant = _tenant_or_404(tenant_id, request.workspace)
    if tenant is None:
        return Response({"error": "Tenant not found"}, status=404)
    if request.method == "GET":
        documents = KycDocument.objects.filter(tenant=tenant, workspace=request.workspace).order_by("-uploaded_at", "-id")
        return Response({"data": KycDocumentSerializer(documents, many=True).data})

    if not request.workspace_membership.role in {"manager", "admin", "owner"}:
        return Response({"error": "Manager-level access required"}, status=403)
    serializer = KycDocumentUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    file = serializer.validated_data["file"]
    try:
        document = upload_document(
            request.user, request.workspace, tenant.id,
            document_type=serializer.validated_data["document_type"],
            file=file,
            content_type=file.content_type or "",
            document_number=serializer.validated_data.get("document_number", ""),
            issued_at=serializer.validated_data.get("issued_at"),
            expires_at=serializer.validated_data.get("expires_at"),
        )
        return Response({"data": KycDocumentSerializer(document).data}, status=201)
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)


@api_view(["POST"])
@permission_classes([WorkspaceManagerPermission])
def kyc_document_review_api(request, document_id):
    serializer = KycDocumentReviewSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        document = review_document(
            request.user, request.workspace, document_id,
            action=serializer.validated_data["action"],
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response({"data": KycDocumentSerializer(document).data})
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceManagerPermission])
def kyc_document_download_api(request, document_id):
    try:
        document = KycDocument.objects.get(id=document_id, workspace=request.workspace)
    except (KycDocument.DoesNotExist, TypeError, ValueError):
        return Response({"error": "KYC document not found"}, status=404)
    storage = CloudinaryPrivateDocumentStorage()
    try:
        stream = storage.open(document.storage_key)
    except PrivateStorageError as exc:
        return Response({"error": str(exc)}, status=404)
    response = FileResponse(stream, content_type=document.content_type)
    response["Content-Length"] = str(document.file_size)
    response["Content-Disposition"] = "attachment; filename=kyc-document"
    return response


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def kyc_document_history_api(request, document_id):
    try:
        document = KycDocument.objects.get(id=document_id, workspace=request.workspace)
    except (KycDocument.DoesNotExist, TypeError, ValueError):
        return Response({"error": "KYC document not found"}, status=404)
    events = KycDocumentEvent.objects.filter(document=document, workspace=request.workspace).order_by("occurred_at", "id")
    return Response({"data": KycDocumentEventSerializer(events, many=True).data})


@api_view(["GET", "POST"])
@permission_classes([WorkspaceManagerPermission])
def kyc_agreements_api(request, tenant_id):
    tenant = _tenant_or_404(tenant_id, request.workspace)
    if tenant is None:
        return Response({"error": "Tenant not found"}, status=404)
    if request.method == "GET":
        links = AgreementLink.objects.filter(tenant=tenant, workspace=request.workspace).order_by("-created_at", "-id")
        return Response({"data": AgreementLinkSerializer(links, many=True).data})
    serializer = AgreementLinkCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    try:
        link = create_agreement_link(
            request.user, request.workspace,
            tenant_id=tenant.id,
            occupancy_id=serializer.validated_data["occupancy"],
            agreement_type=serializer.validated_data["agreement_type"],
            reference=serializer.validated_data.get("reference", ""),
            lease_id=serializer.validated_data.get("lease"),
            metadata=serializer.validated_data.get("metadata"),
        )
        return Response({"data": AgreementLinkSerializer(link).data}, status=201)
    except PermissionDenied as exc:
        return Response({"error": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"error": _error(exc)}, status=400)
