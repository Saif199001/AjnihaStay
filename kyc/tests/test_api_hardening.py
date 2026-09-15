from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from kyc.models import KycDocument, KycProfile
from tenant.models import Tenant
from workspaces.models import Membership, Workspace


class KycApiHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("hard-owner@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("hard-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("hard-staff@example.com", "StrongPass123!")
        self.inactive = User.objects.create_user("hard-inactive@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("hard-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Hardening Workspace", slug="hardening-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Hardening Other", slug="hardening-other", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF)
        Membership.objects.create(workspace=self.workspace, user=self.inactive, role=Membership.ROLE_MANAGER, is_active=False)
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role=Membership.ROLE_OWNER)
        self.tenant = Tenant.objects.create(owner=self.owner, workspace=self.workspace, full_name="Hardening Tenant", phone="9999999999", permanent_address="Delhi")
        self.other_tenant = Tenant.objects.create(owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant", phone="8888888888", permanent_address="Noida")
        self.client = APIClient()

    def _auth(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str((workspace or self.workspace).id)

    def test_anonymous_requests_are_denied(self):
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/")
        self.assertEqual(response.status_code, 401)
        response = self.client.get(f"/api/kyc/documents/999999/download/")
        self.assertEqual(response.status_code, 401)

    def test_inactive_membership_is_denied(self):
        self._auth(self.inactive)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/")
        self.assertEqual(response.status_code, 403)

    def test_get_kyc_does_not_create_profile(self):
        self._auth(self.staff)
        self.assertFalse(KycProfile.objects.filter(tenant=self.tenant).exists())
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], KycProfile.STATUS_UNVERIFIED)
        self.assertFalse(KycProfile.objects.filter(tenant=self.tenant).exists())

    def test_upload_rejects_mime_extension_spoof_before_service(self):
        self._auth(self.manager)
        upload = BytesIO(b"not a pdf")
        upload.name = "identity.pdf"
        upload.size = len(upload.getvalue())
        upload.content_type = "application/pdf"
        with patch("kyc.api.upload_document") as upload_service:
            response = self.client.post(f"/api/tenants/{self.tenant.id}/kyc/documents/", {"document_type": "identity", "file": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        upload_service.assert_not_called()

    def test_upload_rejects_extension_mismatch(self):
        self._auth(self.manager)
        upload = BytesIO(b"%PDF-1.7 valid-looking header")
        upload.name = "identity.png"
        upload.size = len(upload.getvalue())
        upload.content_type = "application/pdf"
        with patch("kyc.api.upload_document") as upload_service:
            response = self.client.post(f"/api/tenants/{self.tenant.id}/kyc/documents/", {"document_type": "identity", "file": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        upload_service.assert_not_called()

    def test_unknown_reject_payload_fields_are_rejected(self):
        self._auth(self.manager)
        response = self.client.post(f"/api/tenants/{self.tenant.id}/kyc/reject/", {"reason": "invalid", "status": "verified"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_illegal_document_transition_is_rejected(self):
        document = KycDocument.objects.create(tenant=self.tenant, workspace=self.workspace, document_type="passport", storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/0123456789abcdef0123456789abcdef", content_type="application/pdf", file_size=100, uploaded_by=self.manager)
        self._auth(self.manager)
        response = self.client.post(f"/api/kyc/documents/{document.id}/review/", {"action": "verify"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cross_workspace_document_review_is_hidden(self):
        document = KycDocument.objects.create(tenant=self.other_tenant, workspace=self.other_workspace, document_type="passport", storage_key=f"kyc/private/workspace/{self.other_workspace.id}/tenant/{self.other_tenant.id}/0123456789abcdef0123456789abcdef", content_type="application/pdf", file_size=100, uploaded_by=self.other_owner)
        self._auth(self.manager)
        response = self.client.post(f"/api/kyc/documents/{document.id}/review/", {"action": "under_review"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_document_and_history_lists_are_bounded_and_paginated(self):
        for index in range(101):
            KycDocument.objects.create(tenant=self.tenant, workspace=self.workspace, document_type=f"doc-{index}", storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/{index + 1:032x}", content_type="application/pdf", file_size=100, uploaded_by=self.manager)
        self._auth(self.staff)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 100)
        self.assertEqual(response.data["pagination"]["count"], 101)
        self.assertEqual(response.data["pagination"]["pages"], 2)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/documents/?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)

    def test_storage_error_does_not_leak_provider_details(self):
        document = KycDocument.objects.create(tenant=self.tenant, workspace=self.workspace, document_type="passport", storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/fedcbafedcbafedcbafedcbafedcbafe", content_type="application/pdf", file_size=4, uploaded_by=self.manager)
        self._auth(self.manager)
        with patch("kyc.api.CloudinaryPrivateDocumentStorage.open", side_effect=Exception("cloudinary-secret-url")):
            response = self.client.get(f"/api/kyc/documents/{document.id}/download/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("cloudinary-secret-url", str(getattr(response, "data", response.content)))
