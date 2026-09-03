from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from .models import Membership, Workspace


class WorkspaceMembershipAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"
        self.owner = User.objects.create_user("owner@example.com", self.password)
        self.workspace = Workspace.objects.create(
            name="Owner Workspace",
            slug="owner-workspace",
            owner=self.owner,
        )
        self.owner_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=Membership.ROLE_OWNER,
        )
        self.staff = User.objects.create_user("staff@example.com", self.password)
        self.manager = User.objects.create_user("manager@example.com", self.password)
        self.admin = User.objects.create_user("admin@example.com", self.password)
        self.other_owner = User.objects.create_user("other-owner@example.com", self.password)
        self.other_workspace = Workspace.objects.create(
            name="Other Workspace",
            slug="other-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(
            workspace=self.other_workspace,
            user=self.other_owner,
            role=Membership.ROLE_OWNER,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_owner_can_add_member(self):
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.staff.email, "role": Membership.ROLE_STAFF},
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        membership = Membership.objects.get(workspace=self.workspace, user=self.staff)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.role, Membership.ROLE_STAFF)

    def test_admin_can_add_member_but_cannot_assign_owner(self):
        Membership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )
        self.authenticate(self.admin)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.staff.email, "role": Membership.ROLE_OWNER},
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.staff).exists())

    def test_manager_and_staff_cannot_manage_members(self):
        manager_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=Membership.ROLE_MANAGER,
        )
        staff_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.staff,
            role=Membership.ROLE_STAFF,
        )

        for user in (self.manager, self.staff):
            self.authenticate(user)
            response = self.client.get(
                "/api/workspaces/members/",
                HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            )
            self.assertEqual(response.status_code, 403)

    def test_member_list_is_workspace_scoped(self):
        Membership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )
        Membership.objects.create(
            workspace=self.other_workspace,
            user=self.staff,
            role=Membership.ROLE_STAFF,
        )
        self.authenticate(self.owner)
        response = self.client.get(
            "/api/workspaces/members/",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["user_id"] for item in response.data["data"]}
        self.assertIn(self.owner.id, returned_ids)
        self.assertIn(self.admin.id, returned_ids)
        self.assertNotIn(self.staff.id, returned_ids)

    def test_owner_cannot_be_demoted(self):
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/workspaces/members/{self.owner.id}/role/",
            {"role": Membership.ROLE_STAFF},
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, Membership.ROLE_OWNER)
        self.assertTrue(self.owner_membership.is_active)

    def test_owner_cannot_be_deactivated(self):
        self.authenticate(self.owner)
        response = self.client.delete(
            f"/api/workspaces/members/{self.owner.id}/deactivate/",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )

        self.assertEqual(response.status_code, 400)
        self.owner_membership.refresh_from_db()
        self.assertTrue(self.owner_membership.is_active)

    def test_cross_workspace_member_role_change_is_blocked(self):
        Membership.objects.create(
            workspace=self.other_workspace,
            user=self.staff,
            role=Membership.ROLE_STAFF,
        )
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/workspaces/members/{self.staff.id}/role/",
            {"role": Membership.ROLE_ADMIN},
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        membership = Membership.objects.get(workspace=self.other_workspace, user=self.staff)
        self.assertEqual(membership.role, Membership.ROLE_STAFF)

    def test_inactive_member_can_be_reactivated_without_duplicate_membership(self):
        membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.staff,
            role=Membership.ROLE_STAFF,
            is_active=False,
        )
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.staff.email, "role": Membership.ROLE_MANAGER},
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.role, Membership.ROLE_MANAGER)
        self.assertEqual(Membership.objects.filter(workspace=self.workspace, user=self.staff).count(), 1)
