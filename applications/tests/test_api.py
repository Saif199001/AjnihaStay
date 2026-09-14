from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from applications.models import Applicant, Application, ApplicationEvent
from properties.models import Property
from workspaces.models import Membership, Workspace


class ApplicationApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("app-api-owner@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("app-api-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("app-api-staff@example.com", "StrongPass123!")
        self.other_owner = User.objects.create_user("app-api-other@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(name="Application API", slug="application-api", owner=self.owner)
        self.other_workspace = Workspace.objects.create(name="Other Application API", slug="other-application-api", owner=self.other_owner)
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF)
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role=Membership.ROLE_OWNER)
        self.property = Property.objects.create(
            owner=self.owner, workspace=self.workspace, name="API Property", property_type="flat",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )
        self.other_property = Property.objects.create(
            owner=self.other_owner, workspace=self.other_workspace, name="Other Property", property_type="flat",
            address="Noida", city="Noida", state="UP", pincode="201301",
        )
        self.applicant = Applicant.objects.create(
            workspace=self.workspace, full_name="API Applicant", phone="9999999999", email="api-applicant@example.com"
        )
        self.other_applicant = Applicant.objects.create(
            workspace=self.other_workspace, full_name="Other Applicant", phone="8888888888"
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(self.workspace.id)

    def test_staff_can_list_applicants_and_applications_but_cannot_create(self):
        self._auth(self.staff)
        self.assertEqual(self.client.get("/api/applicants/").status_code, 200)
        self.assertEqual(self.client.get("/api/applications/").status_code, 200)
        response = self.client.post("/api/applicants/create/", {"full_name": "New", "phone": "7777777777"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_application_and_run_workflow(self):
        self._auth(self.manager)
        response = self.client.post(
            "/api/applications/create/",
            {
                "applicant": self.applicant.id,
                "property": self.property.id,
                "requested_check_in_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        application_id = response.data["data"]["id"]
        self.assertEqual(response.data["data"]["status"], Application.STATUS_DRAFT)

        for action, expected in (("submit", Application.STATUS_SUBMITTED), ("review", Application.STATUS_UNDER_REVIEW), ("approve", Application.STATUS_APPROVED)):
            response = self.client.post(f"/api/applications/{application_id}/{action}/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["data"]["status"], expected)

        history = self.client.get(f"/api/applications/{application_id}/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data["data"]), 3)
        self.assertEqual(ApplicationEvent.objects.filter(application_id=application_id).count(), 3)

    def test_reject_requires_reason_and_exposes_history(self):
        self._auth(self.manager)
        response = self.client.post(
            "/api/applications/create/",
            {"applicant": self.applicant.id, "property": self.property.id},
            format="json",
        )
        application_id = response.data["data"]["id"]
        self.client.post(f"/api/applications/{application_id}/submit/", {}, format="json")
        self.client.post(f"/api/applications/{application_id}/review/", {}, format="json")
        response = self.client.post(f"/api/applications/{application_id}/reject/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            f"/api/applications/{application_id}/reject/", {"reason": "Documents incomplete"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], Application.STATUS_REJECTED)
        self.assertEqual(response.data["data"]["rejection_reason"], "Documents incomplete")

    def test_cross_workspace_objects_are_not_accepted(self):
        self._auth(self.manager)
        response = self.client.post(
            "/api/applications/create/",
            {"applicant": self.other_applicant.id, "property": self.property.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/applications/create/",
            {"applicant": self.applicant.id, "property": self.other_property.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_workspace_application_is_not_visible(self):
        other_application = Application.objects.create(
            workspace=self.other_workspace, applicant=self.other_applicant, property=self.other_property,
            created_by=self.other_owner, updated_by=self.other_owner,
        )
        self._auth(self.manager)
        response = self.client.get(f"/api/applications/{other_application.id}/")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(f"/api/applications/{other_application.id}/history/")
        self.assertEqual(response.status_code, 404)
