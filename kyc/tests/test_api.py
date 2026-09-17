from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from kyc.models import KycDocument, KycProfile
from tenant.models import Tenant
from workspaces.models import Membership, Workspace


class KycApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("api-owner@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("api-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("api-staff@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("api-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="API Workspace", slug="api-workspace", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_VIEWER)
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role=Membership.ROLE_OWNER)
        self.tenant = Tenant.objects.create(
            owner=self.owner, workspace=self.workspace, full_name="API Tenant", phone="9999999999", permanent_address="Delhi"
        )
        self.other_tenant = Tenant.objects.create(
            owner=self.other_owner, workspace=self.other_workspace, full_name="Other Tenant", phone="8888888888", permanent_address="Noida"
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(self.workspace.id)

    def test_staff_can_view_kyc_but_cannot_mutate(self):
        self._auth(self.staff)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], KycProfile.STATUS_UNVERIFIED)
        response = self.client.post(f"/api/tenants/{self.tenant.id}/kyc/submit/", {})
        self.assertEqual(response.status_code, 403)

    def test_cross_workspace_tenant_is_not_visible(self):
        self._auth(self.manager)
        response = self.client.get(f"/api/tenants/{self.other_tenant.id}/kyc/")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(f"/api/tenants/{self.other_tenant.id}/kyc/history/")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(f"/api/tenants/{self.other_tenant.id}/kyc/documents/")
        self.assertEqual(response.status_code, 404)

    def test_document_list_hides_sensitive_number_from_staff(self):
        document = KycDocument.objects.create(
            tenant=self.tenant, workspace=self.workspace, document_type="passport",
            document_number="SECRET-123", storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/0123456789abcdef0123456789abcdef",
            content_type="application/pdf", file_size=100, uploaded_by=self.manager,
        )
        self._auth(self.staff)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("document_number", response.data["data"][0])
        self._auth(self.manager)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["document_number"], "SECRET-123")

    def test_manager_can_upload_and_review_document(self):
        self._auth(self.manager)
        file = SimpleUploadedFile("passport.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        with patch("kyc.api.upload_document") as upload:
            document = KycDocument.objects.create(
                tenant=self.tenant, workspace=self.workspace, document_type="passport",
                storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/abcdefabcdefabcdefabcdefabcdefab",
                content_type="application/pdf", file_size=100, uploaded_by=self.manager,
            )
            upload.return_value = document
            response = self.client.post(
                f"/api/tenants/{self.tenant.id}/kyc/documents/",
                {"document_type": "passport", "file": file},
                format="multipart",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], KycDocument.STATUS_UPLOADED)

        response = self.client.post(
            f"/api/kyc/documents/{document.id}/review/", {"action": "under_review"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_download_sensitive_document(self):
        document = KycDocument.objects.create(
            tenant=self.tenant, workspace=self.workspace, document_type="passport",
            storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/fedcbafedcbafedcbafedcbafedcbafe",
            content_type="application/pdf", file_size=4, uploaded_by=self.manager,
        )
        self._auth(self.staff)
        response = self.client.get(f"/api/kyc/documents/{document.id}/download/")
        self.assertEqual(response.status_code, 403)

    def test_cross_workspace_document_download_is_hidden(self):
        document = KycDocument.objects.create(
            tenant=self.other_tenant, workspace=self.other_workspace, document_type="passport",
            storage_key=f"kyc/private/workspace/{self.other_workspace.id}/tenant/{self.other_tenant.id}/fedcbafedcbafedcbafedcbafedcbafe",
            content_type="application/pdf", file_size=4, uploaded_by=self.other_owner,
        )
        self._auth(self.manager)
        response = self.client.get(f"/api/kyc/documents/{document.id}/download/")
        self.assertEqual(response.status_code, 404)

    def test_download_uses_application_authorization_and_private_storage(self):
        document = KycDocument.objects.create(
            tenant=self.tenant, workspace=self.workspace, document_type="passport",
            storage_key=f"kyc/private/workspace/{self.workspace.id}/tenant/{self.tenant.id}/fedcbafedcbafedcbafedcbafedcbaff",
            content_type="application/pdf", file_size=4, uploaded_by=self.manager,
        )
        self._auth(self.manager)
        with patch("kyc.api.CloudinaryPrivateDocumentStorage.open", return_value=BytesIO(b"test")):
            response = self.client.get(f"/api/kyc/documents/{document.id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertNotIn("cloudinary", response.get("Content-Disposition", "").lower())

    def test_reject_endpoint_requires_reason(self):
        self._auth(self.manager)
        response = self.client.post(f"/api/tenants/{self.tenant.id}/kyc/reject/", {"reason": ""}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_kyc_history_endpoint_is_read_only(self):
        self._auth(self.staff)
        response = self.client.get(f"/api/tenants/{self.tenant.id}/kyc/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])
