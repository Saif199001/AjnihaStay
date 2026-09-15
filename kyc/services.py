"""Canonical service layer for KYC lifecycle and agreement linkage."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from leasing.models import Lease
from tenant.models import Occupancy, Tenant
from workspaces.models import Membership

from .models import AgreementLink, KycDocument, KycDocumentEvent, KycProfile, KycVerificationEvent
from .storage import PrivateStorageError, generate_storage_key


KYC_MANAGER_ROLES = frozenset({Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_MANAGER})
KYC_DOCUMENT_CONTENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})
KYC_DOCUMENT_EXTENSIONS = {
    "application/pdf": frozenset({".pdf"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
}
KYC_DOCUMENT_MAX_SIZE = 10 * 1024 * 1024
KYC_DEFAULT_MIN_SUBMISSION_DOCUMENTS = 1
KYC_DEFAULT_MIN_VERIFIED_DOCUMENTS = 1
KYC_DEFAULT_REQUIRED_DOCUMENT_TYPES = ()


def _require_manager(user, workspace):
    if user is None:
        raise PermissionDenied("KYC mutation requires workspace membership")
    if not Membership.objects.filter(workspace=workspace, user=user, is_active=True, role__in=KYC_MANAGER_ROLES).exists():
        raise PermissionDenied("KYC mutation requires manager-level access")


def _get_tenant(tenant_id, workspace):
    try:
        return Tenant.objects.get(id=tenant_id, workspace=workspace)
    except (Tenant.DoesNotExist, TypeError, ValueError):
        raise ValidationError("Tenant not found")


def _locked_profile(tenant_id, workspace):
    tenant = _get_tenant(tenant_id, workspace)
    profile, _ = KycProfile.objects.select_for_update().get_or_create(
        tenant=tenant, defaults={"workspace": workspace, "status": KycProfile.STATUS_UNVERIFIED}
    )
    if profile.workspace_id != workspace.id:
        raise ValidationError("KYC profile workspace mismatch")
    return profile


def get_or_create_profile(user, workspace, tenant_id):
    _get_tenant(tenant_id, workspace)
    with transaction.atomic():
        return _locked_profile(tenant_id, workspace)


def _append_event(*, profile, actor, from_status, to_status, reason="", metadata=None):
    return KycVerificationEvent.append(
        workspace=profile.workspace, profile=profile, tenant=profile.tenant,
        from_status=from_status, to_status=to_status, actor=actor,
        occurred_at=timezone.now(), reason=reason, metadata=metadata,
        event_key=f"{from_status}:{to_status}:{uuid4().hex}",
    )


def _append_document_event(*, document, actor, from_status, to_status, reason="", metadata=None):
    return KycDocumentEvent.append(
        workspace=document.workspace, document=document, tenant=document.tenant,
        from_status=from_status, to_status=to_status, actor=actor,
        occurred_at=timezone.now(), reason=reason, metadata=metadata,
        event_key=f"{from_status}:{to_status}:{uuid4().hex}",
    )


def _required_document_types():
    configured = getattr(settings, "KYC_REQUIRED_DOCUMENT_TYPES", KYC_DEFAULT_REQUIRED_DOCUMENT_TYPES)
    return frozenset(str(value).strip().lower() for value in configured if str(value).strip())


def _document_policy_counts(tenant):
    documents = KycDocument.objects.filter(tenant=tenant, workspace=tenant.workspace)
    today = timezone.localdate()
    active = documents.exclude(status=KycDocument.STATUS_EXPIRED).exclude(expires_at__lt=today)
    return active, active.filter(status=KycDocument.STATUS_VERIFIED).exclude(expires_at=today)


def _validate_policy_number(setting_name, default):
    try:
        value = int(getattr(settings, setting_name, default))
    except (TypeError, ValueError):
        raise ValidationError(f"{setting_name} policy is invalid")
    if value < 0:
        raise ValidationError(f"{setting_name} policy is invalid")
    return value


def _validate_submission_documents(tenant):
    active, _ = _document_policy_counts(tenant)
    minimum = _validate_policy_number("KYC_MIN_SUBMISSION_DOCUMENTS", KYC_DEFAULT_MIN_SUBMISSION_DOCUMENTS)
    if active.count() < minimum:
        raise ValidationError("Required KYC documents must be uploaded before submission")
    required_types = _required_document_types()
    present = {value.strip().lower() for value in active.values_list("document_type", flat=True)}
    if required_types - present:
        raise ValidationError("Required KYC document types are missing")


def _validate_verification_documents(tenant):
    _, verified = _document_policy_counts(tenant)
    minimum = _validate_policy_number("KYC_MIN_VERIFIED_DOCUMENTS", KYC_DEFAULT_MIN_VERIFIED_DOCUMENTS)
    if verified.count() < minimum:
        raise ValidationError("Required KYC documents must be verified before KYC approval")
    required_types = _required_document_types()
    verified_types = {value.strip().lower() for value in verified.values_list("document_type", flat=True)}
    if required_types - verified_types:
        raise ValidationError("Required KYC document types must be verified before KYC approval")


def submit_kyc(user, workspace, tenant_id):
    _require_manager(user, workspace)
    with transaction.atomic():
        profile = _locked_profile(tenant_id, workspace)
        if profile.status == KycProfile.STATUS_PENDING:
            return profile
        if profile.status not in {KycProfile.STATUS_UNVERIFIED, KycProfile.STATUS_REJECTED}:
            raise ValidationError("KYC profile cannot be submitted from its current status")
        _validate_submission_documents(profile.tenant)
        previous = profile.status
        profile.status = KycProfile.STATUS_PENDING
        profile.verified_at = profile.verified_by = None
        profile.rejected_at = profile.rejected_by = None
        profile.rejection_reason = ""
        profile.save(_allow_lifecycle_mutation=True)
        _append_event(profile=profile, actor=user, from_status=previous, to_status=profile.status)
        return profile


def verify_kyc(user, workspace, tenant_id):
    _require_manager(user, workspace)
    with transaction.atomic():
        profile = _locked_profile(tenant_id, workspace)
        if profile.status == KycProfile.STATUS_VERIFIED:
            return profile
        if profile.status != KycProfile.STATUS_PENDING:
            raise ValidationError("Only pending KYC profiles can be verified")
        _validate_verification_documents(profile.tenant)
        previous = profile.status
        now = timezone.now()
        profile.status = KycProfile.STATUS_VERIFIED
        profile.verified_at = now
        profile.verified_by = user
        profile.rejected_at = profile.rejected_by = None
        profile.rejection_reason = ""
        profile.save(_allow_lifecycle_mutation=True)
        _append_event(profile=profile, actor=user, from_status=previous, to_status=profile.status)
        return profile


def reject_kyc(user, workspace, tenant_id, *, reason):
    _require_manager(user, workspace)
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError("KYC rejection reason is required")
    if len(reason) > 500:
        raise ValidationError("KYC rejection reason cannot exceed 500 characters")
    with transaction.atomic():
        profile = _locked_profile(tenant_id, workspace)
        if profile.status == KycProfile.STATUS_REJECTED and profile.rejection_reason == reason:
            return profile
        if profile.status != KycProfile.STATUS_PENDING:
            raise ValidationError("Only pending KYC profiles can be rejected")
        previous = profile.status
        now = timezone.now()
        profile.status = KycProfile.STATUS_REJECTED
        profile.rejected_at = now
        profile.rejected_by = user
        profile.rejection_reason = reason
        profile.verified_at = profile.verified_by = None
        profile.save(_allow_lifecycle_mutation=True)
        _append_event(profile=profile, actor=user, from_status=previous, to_status=profile.status, reason=reason)
        return profile


def _read_file_prefix(file, size=16):
    try:
        position = file.tell()
        file.seek(0)
        prefix = file.read(size)
        file.seek(position)
    except (AttributeError, OSError, ValueError):
        raise ValidationError("KYC document file cannot be inspected safely")
    if not isinstance(prefix, bytes):
        raise ValidationError("KYC document file cannot be inspected safely")
    return prefix


def _validate_document_file(file, content_type):
    if file is None:
        raise ValidationError("KYC document file is required")
    if content_type not in KYC_DOCUMENT_CONTENT_TYPES:
        raise ValidationError("Unsupported KYC document content type")
    size = getattr(file, "size", None)
    if not isinstance(size, int) or size <= 0:
        raise ValidationError("KYC document file size must be positive")
    if size > KYC_DOCUMENT_MAX_SIZE:
        raise ValidationError("KYC document exceeds the maximum allowed size")
    filename = str(getattr(file, "name", "") or "").strip().lower()
    extension = Path(filename).suffix
    if extension not in KYC_DOCUMENT_EXTENSIONS[content_type]:
        raise ValidationError("KYC document file extension does not match its content type")
    prefix = _read_file_prefix(file)
    signature_ok = {
        "application/pdf": prefix.startswith(b"%PDF-"),
        "image/jpeg": prefix.startswith(b"\xff\xd8\xff"),
        "image/png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
    }[content_type]
    if not signature_ok:
        raise ValidationError("KYC document file content does not match its declared type")
    return size


def upload_document(user, workspace, tenant_id, *, document_type, file, content_type, document_number="", issued_at=None, expires_at=None, storage=None):
    _require_manager(user, workspace)
    document_type = str(document_type or "").strip()
    if not document_type or len(document_type) > 50:
        raise ValidationError("Valid KYC document type is required")
    size = _validate_document_file(file, content_type)
    if issued_at and expires_at and expires_at < issued_at:
        raise ValidationError("Document expiry cannot be before issue date")
    if issued_at and issued_at > date.today():
        raise ValidationError("Document issue date cannot be in the future")
    if expires_at and expires_at <= date.today():
        raise ValidationError("Document expiry date must be in the future")
    storage = storage or __import__("kyc.storage", fromlist=["CloudinaryPrivateDocumentStorage"]).CloudinaryPrivateDocumentStorage()
    with transaction.atomic():
        tenant = _get_tenant(tenant_id, workspace)
        storage_key = generate_storage_key(workspace_id=workspace.id, tenant_id=tenant.id)
        try:
            stored = storage.put(file, storage_key=storage_key, content_type=content_type)
        except PrivateStorageError:
            raise
        try:
            document = KycDocument.objects.create(
                tenant=tenant, workspace=workspace, document_type=document_type,
                document_number=str(document_number or "").strip(), storage_key=stored.storage_key,
                content_type=stored.content_type, file_size=size, status=KycDocument.STATUS_UPLOADED,
                issued_at=issued_at, expires_at=expires_at, uploaded_by=user,
            )
            _append_document_event(document=document, actor=user, from_status="", to_status=KycDocument.STATUS_UPLOADED, metadata={"document_type": document.document_type})
        except Exception:
            try:
                storage.delete(storage_key)
            except Exception:
                pass
            raise
        return document


def review_document(user, workspace, document_id, *, action, reason=""):
    _require_manager(user, workspace)
    action = str(action or "").strip().lower()
    with transaction.atomic():
        try:
            document = KycDocument.objects.select_for_update().get(id=document_id, workspace=workspace)
        except (KycDocument.DoesNotExist, TypeError, ValueError):
            raise ValidationError("KYC document not found")
        if action == "under_review":
            if document.status == KycDocument.STATUS_UNDER_REVIEW:
                return document
            if document.status != KycDocument.STATUS_UPLOADED:
                raise ValidationError("Only uploaded documents can enter review")
            previous = document.status
            document.status = KycDocument.STATUS_UNDER_REVIEW
        elif action == "verify":
            if document.status == KycDocument.STATUS_VERIFIED:
                return document
            if document.status != KycDocument.STATUS_UNDER_REVIEW:
                raise ValidationError("Only documents under review can be verified")
            if document.expires_at and document.expires_at <= timezone.localdate():
                raise ValidationError("Expired documents cannot be verified")
            previous = document.status
            document.status = KycDocument.STATUS_VERIFIED
            document.verified_at = timezone.now()
            document.verified_by = user
            document.rejected_at = document.rejected_by = None
            document.rejection_reason = ""
        elif action == "reject":
            reason = str(reason or "").strip()
            if not reason:
                raise ValidationError("KYC document rejection reason is required")
            if len(reason) > 500:
                raise ValidationError("KYC document rejection reason cannot exceed 500 characters")
            if document.status == KycDocument.STATUS_REJECTED and document.rejection_reason == reason:
                return document
            if document.status not in {KycDocument.STATUS_UPLOADED, KycDocument.STATUS_UNDER_REVIEW}:
                raise ValidationError("Only uploaded or under-review documents can be rejected")
            previous = document.status
            document.status = KycDocument.STATUS_REJECTED
            document.rejected_at = timezone.now()
            document.rejected_by = user
            document.rejection_reason = reason
            document.verified_at = document.verified_by = None
        else:
            raise ValidationError("Unsupported KYC document review action")
        document.save(_allow_lifecycle_mutation=True)
        _append_document_event(document=document, actor=user, from_status=previous, to_status=document.status, reason=reason if action == "reject" else "")
        return document


def expire_document(user, workspace, document_id, *, reason="Document validity period ended"):
    _require_manager(user, workspace)
    reason = str(reason or "").strip()
    if len(reason) > 500:
        raise ValidationError("KYC document expiry reason cannot exceed 500 characters")
    with transaction.atomic():
        try:
            document = KycDocument.objects.select_for_update().get(id=document_id, workspace=workspace)
        except (KycDocument.DoesNotExist, TypeError, ValueError):
            raise ValidationError("KYC document not found")
        if document.status == KycDocument.STATUS_EXPIRED:
            return document
        if document.status != KycDocument.STATUS_VERIFIED:
            raise ValidationError("Only verified documents can expire")
        if not document.expires_at or document.expires_at > timezone.localdate():
            raise ValidationError("Document has not reached its expiry date")
        previous = document.status
        document.status = KycDocument.STATUS_EXPIRED
        document.save(_allow_lifecycle_mutation=True)
        _append_document_event(document=document, actor=user, from_status=previous, to_status=document.status, reason=reason)
        return document


def create_agreement_link(user, workspace, *, tenant_id, occupancy_id, agreement_type, reference="", lease_id=None, metadata=None):
    _require_manager(user, workspace)
    agreement_type = str(agreement_type or "").strip()
    if not agreement_type or len(agreement_type) > 50:
        raise ValidationError("Valid agreement type is required")
    with transaction.atomic():
        tenant = _get_tenant(tenant_id, workspace)
        try:
            occupancy = Occupancy.objects.select_for_update().get(id=occupancy_id, tenant=tenant)
        except (Occupancy.DoesNotExist, TypeError, ValueError):
            raise ValidationError("Occupancy not found")
        lease = None
        if lease_id is not None:
            try:
                lease = Lease.objects.get(id=lease_id, workspace=workspace, occupancy=occupancy)
            except (Lease.DoesNotExist, TypeError, ValueError):
                raise ValidationError("Lease not found for the selected occupancy")
        link, created = AgreementLink.objects.get_or_create(
            workspace=workspace, tenant=tenant, occupancy=occupancy, lease=lease,
            agreement_type=agreement_type, reference=str(reference or "").strip(),
            defaults={"metadata": metadata or {}, "created_by": user},
        )
        if not created and metadata:
            raise ValidationError("Agreement link already exists")
        return link
