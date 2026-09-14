from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from kyc.models import AgreementLink, KycDocument, KycDocumentEvent, KycProfile, KycVerificationEvent
from kyc.services import (
    create_agreement_link,
    expire_document,
    get_or_create_profile,
    reject_kyc,
    review_document,
    submit_kyc,
    verify_kyc,
)
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class KycServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("kyc-owner@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("kyc-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("kyc-staff@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="KYC Workspace", slug="kyc-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF)
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="KYC Tenant", phone="9999999999", permanent_address="Delhi")

    def _uploaded_document(self, document_type="passport", expires_at=None):
        return KycDocument.objects.create(
            tenant=self.tenant, workspace=self.workspace, document_type=document_type,
            storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/0123456789abcdef0123456789abcdef",
            content_type="application/pdf", file_size=100, uploaded_by=self.manager,
            expires_at=expires_at,
        )

    def test_profile_is_created_unverified_and_is_workspace_scoped(self):
        profile = get_or_create_profile(self.staff, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_UNVERIFIED)
        self.assertEqual(profile.workspace_id, self.workspace.id)
        self.assertEqual(KycProfile.objects.count(), 1)

    def test_submit_verify_and_history_are_canonical(self):
        self._uploaded_document()
        profile = submit_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_PENDING)
        with self.assertRaises(ValidationError):
            verify_kyc(self.manager, self.workspace, self.tenant.id)
        document = self._uploaded_document("pan")
        review_document(self.manager, self.workspace, document.id, action="under_review")
        review_document(self.manager, self.workspace, document.id, action="verify")
        profile = verify_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_VERIFIED)
        profile.refresh_from_db()
        self.assertEqual(profile.verified_by_id, self.manager.id)
        self.assertEqual(KycVerificationEvent.objects.filter(kyc_profile=profile).count(), 2)

    def test_submit_requires_at_least_one_document(self):
        with self.assertRaises(ValidationError):
            submit_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(KycVerificationEvent.objects.count(), 0)

    @override_settings(KYC_REQUIRED_DOCUMENT_TYPES=("passport", "pan"))
    def test_required_document_types_are_enforced(self):
        self._uploaded_document("passport")
        with self.assertRaises(ValidationError):
            submit_kyc(self.manager, self.workspace, self.tenant.id)
        self._uploaded_document("pan")
        submit_kyc(self.manager, self.workspace, self.tenant.id)
        passport = KycDocument.objects.get(document_type="passport")
        pan = KycDocument.objects.get(document_type="pan")
        for document in (passport, pan):
            review_document(self.manager, self.workspace, document.id, action="under_review")
            review_document(self.manager, self.workspace, document.id, action="verify")
        verify_kyc(self.manager, self.workspace, self.tenant.id)

    def test_reject_requires_reason_and_rejected_can_resubmit(self):
        self._uploaded_document()
        submit_kyc(self.manager, self.workspace, self.tenant.id)
        with self.assertRaises(ValidationError):
            reject_kyc(self.manager, self.workspace, self.tenant.id, reason="")
        reject_kyc(self.manager, self.workspace, self.tenant.id, reason="Document mismatch")
        profile = submit_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_PENDING)
        self.assertEqual(KycVerificationEvent.objects.filter(kyc_profile=profile).count(), 3)

    def test_verified_profile_cannot_be_downgraded_by_service(self):
        document = self._uploaded_document()
        submit_kyc(self.manager, self.workspace, self.tenant.id)
        review_document(self.manager, self.workspace, document.id, action="under_review")
        review_document(self.manager, self.workspace, document.id, action="verify")
        verify_kyc(self.manager, self.workspace, self.tenant.id)
        with self.assertRaises(ValidationError):
            reject_kyc(self.manager, self.workspace, self.tenant.id, reason="No longer valid")

    def test_staff_cannot_change_kyc_lifecycle(self):
        with self.assertRaises(PermissionDenied):
            submit_kyc(self.staff, self.workspace, self.tenant.id)

    def test_profile_direct_status_mutation_is_blocked(self):
        profile = get_or_create_profile(self.staff, self.workspace, self.tenant.id)
        profile.status = KycProfile.STATUS_PENDING
        with self.assertRaises(ValidationError):
            profile.save()
        with self.assertRaises(ValidationError):
            KycProfile.objects.filter(pk=profile.pk).update(status=KycProfile.STATUS_PENDING)

    def test_profile_direct_terminal_creation_is_blocked(self):
        with self.assertRaises(ValidationError):
            KycProfile.objects.create(tenant=self.tenant, workspace=self.workspace, status=KycProfile.STATUS_VERIFIED, verified_at=timezone.now(), verified_by=self.manager)
        with self.assertRaises(ValidationError):
            KycProfile.objects.create(tenant=self.tenant, workspace=self.workspace, status=KycProfile.STATUS_REJECTED, rejected_at=timezone.now(), rejected_by=self.manager, rejection_reason="Rejected")

    def test_document_review_requires_valid_transition(self):
        document = self._uploaded_document()
        document = review_document(self.manager, self.workspace, document.id, action="under_review")
        self.assertEqual(document.status, KycDocument.STATUS_UNDER_REVIEW)
        document = review_document(self.manager, self.workspace, document.id, action="verify")
        self.assertEqual(document.status, KycDocument.STATUS_VERIFIED)
        self.assertIsNotNone(document.verified_at)
        self.assertEqual(document.verified_by_id, self.manager.id)
        self.assertEqual(KycDocumentEvent.objects.filter(document=document).count(), 3)

    def test_document_direct_lifecycle_creation_is_blocked(self):
        base = {
            "tenant": self.tenant, "workspace": self.workspace, "document_type": "passport",
            "storage_key": f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/0123456789abcdef0123456789abcdef",
            "content_type": "application/pdf", "file_size": 100, "uploaded_by": self.manager,
        }
        for status in (KycDocument.STATUS_UNDER_REVIEW, KycDocument.STATUS_VERIFIED, KycDocument.STATUS_REJECTED, KycDocument.STATUS_EXPIRED):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                KycDocument.objects.create(**base, status=status)

    def test_document_audit_fields_cannot_be_mutated_directly(self):
        document = self._uploaded_document(expires_at=timezone.localdate() + timedelta(days=10))
        document.expires_at = timezone.localdate() + timedelta(days=20)
        with self.assertRaises(ValidationError):
            document.save()
        with self.assertRaises(ValidationError):
            KycDocument.objects.filter(pk=document.pk).update(expires_at=timezone.localdate() + timedelta(days=20))
        document.refresh_from_db()
        self.assertEqual(document.expires_at, timezone.localdate() + timedelta(days=10))

    def test_verification_history_cannot_be_created_or_bulk_created_directly(self):
        profile = get_or_create_profile(self.staff, self.workspace, self.tenant.id)
        fields = {
            "workspace": self.workspace, "kyc_profile": profile, "tenant": self.tenant,
            "from_status": KycProfile.STATUS_UNVERIFIED, "to_status": KycProfile.STATUS_PENDING,
            "actor": self.manager, "occurred_at": timezone.now(), "event_key": "direct-test",
        }
        with self.assertRaises(ValidationError):
            KycVerificationEvent.objects.create(**fields)
        with self.assertRaises(ValidationError):
            KycVerificationEvent.objects.bulk_create([KycVerificationEvent(**fields)])
        self.assertEqual(KycVerificationEvent.objects.count(), 0)

    def test_document_history_is_immutable_and_canonical(self):
        document = self._uploaded_document()
        events = list(KycDocumentEvent.objects.filter(document=document).order_by("id"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].from_status, "")
        self.assertEqual(events[0].to_status, KycDocument.STATUS_UPLOADED)
        review_document(self.manager, self.workspace, document.id, action="under_review")
        events = list(KycDocumentEvent.objects.filter(document=document).order_by("id"))
        self.assertEqual(len(events), 2)
        event = events[-1]
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            KycDocumentEvent.objects.filter(pk=event.pk).update(reason="tampered")
        with self.assertRaises(ValidationError):
            KycDocumentEvent.objects.filter(pk=event.pk).delete()
        fields = {
            "workspace": self.workspace, "document": document, "tenant": self.tenant,
            "from_status": KycDocument.STATUS_UPLOADED, "to_status": KycDocument.STATUS_UNDER_REVIEW,
            "actor": self.manager, "occurred_at": timezone.now(), "event_key": "direct-test",
        }
        with self.assertRaises(ValidationError):
            KycDocumentEvent.objects.create(**fields)
        with self.assertRaises(ValidationError):
            KycDocumentEvent.objects.bulk_create([KycDocumentEvent(**fields)])

    def test_document_expiry_requires_verified_document_and_expiry_date(self):
        today = timezone.localdate()
        document = self._uploaded_document(expires_at=today)
        review_document(self.manager, self.workspace, document.id, action="under_review")
        with self.assertRaises(ValidationError):
            review_document(self.manager, self.workspace, document.id, action="verify")

        future = today + timedelta(days=1)
        document = self._uploaded_document("pan", expires_at=future)
        review_document(self.manager, self.workspace, document.id, action="under_review")
        review_document(self.manager, self.workspace, document.id, action="verify")
        with patch("kyc.services.timezone.localdate", return_value=future):
            document = expire_document(self.manager, self.workspace, document.id)
            self.assertEqual(document.status, KycDocument.STATUS_EXPIRED)
            self.assertEqual(KycDocumentEvent.objects.filter(document=document).count(), 4)
            self.assertEqual(expire_document(self.manager, self.workspace, document.id).status, KycDocument.STATUS_EXPIRED)

    def test_expired_document_is_not_accepted_for_kyc_verification(self):
        today = timezone.localdate()
        document = self._uploaded_document(expires_at=today + timedelta(days=1))
        submit_kyc(self.manager, self.workspace, self.tenant.id)
        review_document(self.manager, self.workspace, document.id, action="under_review")
        review_document(self.manager, self.workspace, document.id, action="verify")
        with patch("kyc.services.timezone.localdate", return_value=today + timedelta(days=1)):
            with self.assertRaises(ValidationError):
                verify_kyc(self.manager, self.workspace, self.tenant.id)

    def test_agreement_link_duplicate_is_idempotent(self):
        unit = Unit.objects.create(property=self._property(), unit_type="room", unit_number="K1", rent=Decimal("10000.00"))
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=timezone.localdate(), next_due_date=timezone.localdate())
        first = create_agreement_link(self.manager, self.workspace, tenant_id=self.tenant.id, occupancy_id=occupancy.id, agreement_type="rental_agreement", reference="AGR-1")
        second = create_agreement_link(self.manager, self.workspace, tenant_id=self.tenant.id, occupancy_id=occupancy.id, agreement_type="rental_agreement", reference="AGR-1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AgreementLink.objects.count(), 1)

        duplicate = AgreementLink(
            workspace=self.workspace, tenant=self.tenant, occupancy=occupancy,
            agreement_type="rental_agreement", reference="AGR-1", created_by=self.manager,
        )
        with self.assertRaises(IntegrityError):
            with self.captureOnCommitCallbacks(execute=True):
                duplicate.save()

    def test_agreement_link_requires_matching_workspace_and_occupancy(self):
        unit = Unit.objects.create(property=self._property(), unit_type="room", unit_number="K1", rent=Decimal("10000.00"))
        occupancy = Occupancy.objects.create(tenant=self.tenant, unit=unit, allotted_by=self.owner, rent=Decimal("10000.00"), check_in_date=timezone.localdate(), next_due_date=timezone.localdate())
        link = create_agreement_link(self.manager, self.workspace, tenant_id=self.tenant.id, occupancy_id=occupancy.id, agreement_type="rental_agreement", reference="AGR-1")
        self.assertEqual(link.tenant_id, self.tenant.id)
        self.assertEqual(link.occupancy_id, occupancy.id)
        self.assertEqual(AgreementLink.objects.count(), 1)

    def _property(self):
        from properties.models import Property
        return Property.objects.create(owner=self.owner, workspace=self.workspace, name="KYC Property", property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001")
