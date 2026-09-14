from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from unittest.mock import Mock

from accounts.models import User
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace

from kyc.models import AgreementLink, KycDocument, KycProfile, KycVerificationEvent
from kyc.services import create_agreement_link, get_or_create_profile, reject_kyc, review_document, submit_kyc, verify_kyc


class KycServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("kyc-owner@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("kyc-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("kyc-staff@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="KYC Workspace", slug="kyc-workspace", owner=self.owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF)
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="KYC Tenant",
            phone="9999999999", permanent_address="Delhi",
        )

    def test_profile_is_created_unverified_and_is_workspace_scoped(self):
        profile = get_or_create_profile(self.staff, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_UNVERIFIED)
        self.assertEqual(profile.workspace_id, self.workspace.id)
        self.assertEqual(KycProfile.objects.count(), 1)

    def test_submit_verify_and_history_are_canonical(self):
        profile = submit_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_PENDING)
        profile = verify_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_VERIFIED)
        profile.refresh_from_db()
        self.assertEqual(profile.verified_by_id, self.manager.id)
        self.assertEqual(KycVerificationEvent.objects.filter(kyc_profile=profile).count(), 2)

    def test_reject_requires_reason_and_rejected_can_resubmit(self):
        submit_kyc(self.manager, self.workspace, self.tenant.id)
        with self.assertRaises(ValidationError):
            reject_kyc(self.manager, self.workspace, self.tenant.id, reason="")
        reject_kyc(self.manager, self.workspace, self.tenant.id, reason="Document mismatch")
        profile = submit_kyc(self.manager, self.workspace, self.tenant.id)
        self.assertEqual(profile.status, KycProfile.STATUS_PENDING)
        self.assertEqual(KycVerificationEvent.objects.filter(kyc_profile=profile).count(), 3)

    def test_verified_profile_cannot_be_downgraded_by_service(self):
        submit_kyc(self.manager, self.workspace, self.tenant.id)
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

    def test_document_review_requires_valid_transition(self):
        document = KycDocument.objects.create(
            tenant=self.tenant, workspace=self.workspace, document_type="passport",
            storage_key="kyc/private/workspace/1/tenant/1/0123456789abcdef0123456789abcdef",
            content_type="application/pdf", file_size=100, uploaded_by=self.manager,
        )
        document = review_document(self.manager, self.workspace, document.id, action="under_review")
        self.assertEqual(document.status, KycDocument.STATUS_UNDER_REVIEW)
        document = review_document(self.manager, self.workspace, document.id, action="verify")
        self.assertEqual(document.status, KycDocument.STATUS_VERIFIED)
        self.assertIsNotNone(document.verified_at)
        self.assertEqual(document.verified_by_id, self.manager.id)

    def test_agreement_link_requires_matching_workspace_and_occupancy(self):
        unit = Unit.objects.create(
            property=self._property(), unit_type="room", unit_number="K1", rent="10000.00"
        )
        occupancy = Occupancy.objects.create(
            tenant=self.tenant, unit=unit, allotted_by=self.owner, rent="10000.00",
            check_in_date=timezone.localdate(), next_due_date=timezone.localdate(),
        )
        link = create_agreement_link(
            self.manager, self.workspace, tenant_id=self.tenant.id,
            occupancy_id=occupancy.id, agreement_type="rental_agreement", reference="AGR-1",
        )
        self.assertEqual(link.tenant_id, self.tenant.id)
        self.assertEqual(link.occupancy_id, occupancy.id)
        self.assertEqual(AgreementLink.objects.count(), 1)

    def _property(self):
        from properties.models import Property
        return Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="KYC Property",
            property_type="pg", address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
