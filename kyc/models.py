from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class LifecycleProtectedQuerySet(models.QuerySet):
    lifecycle_fields = frozenset()

    def update(self, **kwargs):
        blocked = self.lifecycle_fields.intersection(kwargs)
        if blocked:
            raise ValidationError("KYC lifecycle fields must be changed through the canonical service")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        blocked = self.lifecycle_fields.intersection(fields)
        if blocked:
            raise ValidationError("KYC lifecycle fields must be changed through the canonical service")
        return super().bulk_update(objs, fields, batch_size=batch_size)


class KycProfileQuerySet(LifecycleProtectedQuerySet):
    lifecycle_fields = frozenset({"status"})


class KycDocumentQuerySet(LifecycleProtectedQuerySet):
    lifecycle_fields = frozenset({
        "status", "document_type", "document_number", "storage_key", "content_type", "file_size",
        "uploaded_by", "uploaded_at", "issued_at", "expires_at", "verified_at", "verified_by",
        "rejected_at", "rejected_by", "rejection_reason",
    })


class ImmutableQuerySet(models.QuerySet):
    def create(self, **kwargs):
        raise ValidationError("KYC history must be appended through the canonical service")

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        raise ValidationError("KYC history must be appended through the canonical service")

    def update(self, **kwargs):
        raise ValidationError("KYC history is immutable")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("KYC history is immutable")

    def delete(self):
        raise ValidationError("KYC history is immutable")


class KycProfile(models.Model):
    STATUS_UNVERIFIED = "unverified"
    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_UNVERIFIED, "Unverified"),
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_REJECTED, "Rejected"),
    )

    tenant = models.OneToOneField("tenant.Tenant", on_delete=models.PROTECT, related_name="kyc_profile")
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="kyc_profiles")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNVERIFIED)
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="kyc_profiles_verified")
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="kyc_profiles_rejected")
    rejection_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = KycProfileQuerySet.as_manager()

    def clean(self):
        if self.tenant_id and self.workspace_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("KYC profile tenant and workspace must match")
        if self.status == self.STATUS_VERIFIED:
            if not self.verified_at or not self.verified_by_id:
                raise ValidationError("Verified KYC profile requires verification metadata")
            if self.rejected_at or self.rejected_by_id or self.rejection_reason:
                raise ValidationError("Verified KYC profile cannot contain rejection metadata")
        if self.status == self.STATUS_REJECTED:
            if not self.rejected_at or not self.rejected_by_id or not self.rejection_reason.strip():
                raise ValidationError("Rejected KYC profile requires rejection metadata")
            if self.verified_at or self.verified_by_id:
                raise ValidationError("Rejected KYC profile cannot contain verification metadata")
        if self.status in {self.STATUS_UNVERIFIED, self.STATUS_PENDING} and (
            self.verified_at or self.verified_by_id or self.rejected_at or self.rejected_by_id or self.rejection_reason
        ):
            raise ValidationError("Non-terminal KYC profile cannot contain terminal audit metadata")

    def save(self, *args, **kwargs):
        allow_lifecycle = kwargs.pop("_allow_lifecycle_mutation", False)
        if self.pk and not allow_lifecycle:
            previous = type(self).objects.filter(pk=self.pk).values(*KycProfileQuerySet.lifecycle_fields).first()
            if previous and previous["status"] != self.status:
                raise ValidationError("KYC lifecycle status must be changed through the canonical service")
        if not self.pk and self.status in {self.STATUS_VERIFIED, self.STATUS_REJECTED}:
            raise ValidationError("KYC terminal lifecycle state must be reached through the canonical service")
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["unverified", "pending", "verified", "rejected"]), name="kyc_profile_status_valid"),
        ]
        indexes = [models.Index(fields=["workspace", "status"])]


class KycDocument(models.Model):
    STATUS_UPLOADED = "uploaded"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_UNDER_REVIEW, "Under review"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_EXPIRED, "Expired"),
    )

    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.PROTECT, related_name="kyc_documents")
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="kyc_documents")
    document_type = models.CharField(max_length=50)
    document_number = models.CharField(max_length=100, blank=True, default="")
    storage_key = models.CharField(max_length=500)
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveBigIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    issued_at = models.DateField(blank=True, null=True)
    expires_at = models.DateField(blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kyc_documents_uploaded")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="kyc_documents_verified")
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="kyc_documents_rejected")
    rejection_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = KycDocumentQuerySet.as_manager()

    def clean(self):
        if self.tenant_id and self.workspace_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("KYC document tenant and workspace must match")
        if self.issued_at and self.expires_at and self.expires_at < self.issued_at:
            raise ValidationError("Document expiry cannot be before issue date")
        if self.file_size <= 0:
            raise ValidationError("KYC document file size must be positive")
        if self.status == self.STATUS_VERIFIED and (not self.verified_at or not self.verified_by_id):
            raise ValidationError("Verified document requires verification metadata")
        if self.status == self.STATUS_REJECTED and (not self.rejected_at or not self.rejected_by_id or not self.rejection_reason.strip()):
            raise ValidationError("Rejected document requires rejection metadata")
        if self.status == self.STATUS_EXPIRED and not self.expires_at:
            raise ValidationError("Expired document requires an expiry date")

    def save(self, *args, **kwargs):
        allow_lifecycle = kwargs.pop("_allow_lifecycle_mutation", False)
        if self.pk and not allow_lifecycle:
            previous = type(self).objects.filter(pk=self.pk).values(*KycDocumentQuerySet.lifecycle_fields).first()
            if previous:
                changed = {field for field in KycDocumentQuerySet.lifecycle_fields if previous[field] != getattr(self, field)}
                if changed:
                    raise ValidationError("KYC document lifecycle and audit fields must be changed through the canonical service")
        if not self.pk and self.status in {self.STATUS_UNDER_REVIEW, self.STATUS_VERIFIED, self.STATUS_REJECTED, self.STATUS_EXPIRED}:
            raise ValidationError("KYC document lifecycle state must be reached through the canonical service")
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["uploaded", "under_review", "verified", "rejected", "expired"]), name="kyc_document_status_valid"),
            models.CheckConstraint(condition=Q(file_size__gt=0), name="kyc_document_size_positive"),
            models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(issued_at__isnull=True) | Q(expires_at__gte=F("issued_at")), name="kyc_document_expiry_valid"),
        ]
        indexes = [models.Index(fields=["workspace", "tenant", "status"]), models.Index(fields=["workspace", "expires_at"])]


class KycVerificationEvent(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="kyc_verification_events")
    kyc_profile = models.ForeignKey(KycProfile, on_delete=models.PROTECT, related_name="verification_events")
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.PROTECT, related_name="kyc_verification_events")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kyc_verification_events")
    occurred_at = models.DateTimeField()
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    event_key = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    def clean(self):
        if self.kyc_profile_id and self.tenant_id and self.kyc_profile.tenant_id != self.tenant_id:
            raise ValidationError("KYC event profile and tenant must match")
        if self.kyc_profile_id and self.workspace_id and self.kyc_profile.workspace_id != self.workspace_id:
            raise ValidationError("KYC event profile and workspace must match")
        if self.tenant_id and self.workspace_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("KYC event tenant and workspace must match")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("KYC verification history is immutable")
        raise ValidationError("KYC verification history must be appended through the canonical service")

    @classmethod
    def append(cls, *, workspace, profile, tenant, from_status, to_status, actor, occurred_at, reason="", metadata=None, event_key):
        event = cls(
            workspace=workspace, kyc_profile=profile, tenant=tenant,
            from_status=from_status, to_status=to_status, actor=actor,
            occurred_at=occurred_at, reason=reason, metadata=metadata or {}, event_key=event_key,
        )
        event.clean()
        models.Model.save(event, force_insert=True)
        return event

    def delete(self, *args, **kwargs):
        raise ValidationError("KYC verification history is immutable")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kyc_profile", "event_key"], name="kyc_event_profile_key_uniq")]
        indexes = [models.Index(fields=["workspace", "tenant", "occurred_at"])]


class KycDocumentEvent(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="kyc_document_events")
    document = models.ForeignKey(KycDocument, on_delete=models.PROTECT, related_name="lifecycle_events")
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.PROTECT, related_name="kyc_document_events")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kyc_document_events")
    occurred_at = models.DateTimeField()
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    event_key = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    def clean(self):
        if self.document_id and self.tenant_id and self.document.tenant_id != self.tenant_id:
            raise ValidationError("KYC document event and tenant must match")
        if self.document_id and self.workspace_id and self.document.workspace_id != self.workspace_id:
            raise ValidationError("KYC document event and workspace must match")
        if self.tenant_id and self.workspace_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("KYC document event tenant and workspace must match")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("KYC document history is immutable")
        raise ValidationError("KYC document history must be appended through the canonical service")

    @classmethod
    def append(cls, *, workspace, document, tenant, from_status, to_status, actor, occurred_at, reason="", metadata=None, event_key):
        event = cls(
            workspace=workspace, document=document, tenant=tenant,
            from_status=from_status, to_status=to_status, actor=actor,
            occurred_at=occurred_at, reason=reason, metadata=metadata or {}, event_key=event_key,
        )
        event.clean()
        models.Model.save(event, force_insert=True)
        return event

    def delete(self, *args, **kwargs):
        raise ValidationError("KYC document history is immutable")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "event_key"], name="kyc_doc_event_key_uniq")]
        indexes = [models.Index(fields=["workspace", "tenant", "occurred_at"])]


class AgreementLink(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="agreement_links")
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.PROTECT, related_name="agreement_links")
    occupancy = models.ForeignKey("tenant.Occupancy", on_delete=models.PROTECT, related_name="agreement_links")
    lease = models.ForeignKey("leasing.Lease", on_delete=models.PROTECT, blank=True, null=True, related_name="agreement_links")
    agreement_type = models.CharField(max_length=50)
    reference = models.CharField(max_length=500, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agreement_links_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.tenant_id and self.workspace_id and self.tenant.workspace_id != self.workspace_id:
            raise ValidationError("Agreement tenant and workspace must match")
        if self.occupancy_id and self.workspace_id and self.occupancy.tenant.workspace_id != self.workspace_id:
            raise ValidationError("Agreement occupancy and workspace must match")
        if self.occupancy_id and self.occupancy.tenant_id != self.tenant_id:
            raise ValidationError("Agreement tenant and occupancy must match")
        if self.lease_id:
            if self.lease.occupancy_id != self.occupancy_id:
                raise ValidationError("Agreement lease must belong to the selected occupancy")
            if self.lease.workspace_id != self.workspace_id:
                raise ValidationError("Agreement lease and workspace must match")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "tenant", "occupancy", "agreement_type", "reference"], name="agreement_link_logical_uniq")]
        indexes = [models.Index(fields=["workspace", "tenant"]), models.Index(fields=["workspace", "occupancy"]), models.Index(fields=["workspace", "lease"])]
