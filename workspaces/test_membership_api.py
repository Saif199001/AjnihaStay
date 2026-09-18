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
        self.viewer = User.objects.create_user("viewer@example.com", self.password)
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

    def workspace_headers(self):
        return {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

    def test_owner_can_add_member_as_viewer(self):
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.viewer.email, "role": Membership.ROLE_VIEWER},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 201)
        membership = Membership.objects.get(workspace=self.workspace, user=self.viewer)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.role, Membership.ROLE_VIEWER)

    def test_legacy_staff_role_is_rejected(self):
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.viewer.email, "role": "staff"},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.viewer).exists())

    def test_admin_can_add_member_but_cannot_assign_owner(self):
        Membership.objects.create(workspace=self.workspace, user=self.admin, role=Membership.ROLE_ADMIN)
        self.authenticate(self.admin)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.viewer.email, "role": Membership.ROLE_OWNER},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.viewer).exists())

    def test_manager_and_viewer_cannot_manage_members(self):
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role=Membership.ROLE_VIEWER)

        for user in (self.manager, self.viewer):
            self.authenticate(user)
            response = self.client.get("/api/workspaces/members/", **self.workspace_headers())
            self.assertEqual(response.status_code, 403)

    def test_member_list_is_workspace_scoped(self):
        Membership.objects.create(workspace=self.workspace, user=self.admin, role=Membership.ROLE_ADMIN)
        Membership.objects.create(workspace=self.other_workspace, user=self.viewer, role=Membership.ROLE_VIEWER)
        self.authenticate(self.owner)
        response = self.client.get("/api/workspaces/members/", **self.workspace_headers())

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["user_id"] for item in response.data["data"]}
        self.assertIn(self.owner.id, returned_ids)
        self.assertIn(self.admin.id, returned_ids)
        self.assertNotIn(self.viewer.id, returned_ids)

    def test_owner_cannot_be_demoted(self):
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/workspaces/members/{self.owner.id}/role/",
            {"role": Membership.ROLE_VIEWER},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, Membership.ROLE_OWNER)
        self.assertTrue(self.owner_membership.is_active)

    def test_owner_cannot_be_deactivated(self):
        self.authenticate(self.owner)
        response = self.client.delete(
            f"/api/workspaces/members/{self.owner.id}/deactivate/", **self.workspace_headers()
        )

        self.assertEqual(response.status_code, 400)
        self.owner_membership.refresh_from_db()
        self.assertTrue(self.owner_membership.is_active)

    def test_cross_workspace_member_role_change_is_blocked(self):
        Membership.objects.create(workspace=self.other_workspace, user=self.viewer, role=Membership.ROLE_VIEWER)
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/workspaces/members/{self.viewer.id}/role/",
            {"role": Membership.ROLE_ADMIN},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 400)
        membership = Membership.objects.get(workspace=self.other_workspace, user=self.viewer)
        self.assertEqual(membership.role, Membership.ROLE_VIEWER)

    def test_inactive_member_can_be_reactivated_without_duplicate_membership(self):
        membership = Membership.objects.create(
            workspace=self.workspace, user=self.viewer, role=Membership.ROLE_VIEWER, is_active=False
        )
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/members/",
            {"email": self.viewer.email, "role": Membership.ROLE_MANAGER},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 201)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.role, Membership.ROLE_MANAGER)
        self.assertEqual(Membership.objects.filter(workspace=self.workspace, user=self.viewer).count(), 1)

    def test_owner_can_transfer_ownership_to_active_member(self):
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role=Membership.ROLE_MANAGER)
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/workspaces/current/transfer-ownership/",
            {"target_user_id": self.viewer.id},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.workspace.refresh_from_db()
        self.owner_membership.refresh_from_db()
        target = Membership.objects.get(workspace=self.workspace, user=self.viewer)
        self.assertEqual(self.workspace.owner_id, self.viewer.id)
        self.assertEqual(self.owner_membership.role, Membership.ROLE_ADMIN)
        self.assertEqual(target.role, Membership.ROLE_OWNER)

    def test_non_owner_cannot_transfer_ownership(self):
        Membership.objects.create(workspace=self.workspace, user=self.admin, role=Membership.ROLE_ADMIN)
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role=Membership.ROLE_VIEWER)
        self.authenticate(self.admin)
        response = self.client.post(
            "/api/workspaces/current/transfer-ownership/",
            {"target_user_id": self.viewer.id},
            **self.workspace_headers(), format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.owner_id, self.owner.id)

    def test_membership_admin_form_locks_existing_identity_fields(self):
        from .admin import MembershipAdminForm

        form = MembershipAdminForm(instance=self.owner_membership)
        self.assertTrue(form.fields["workspace"].disabled)
        self.assertTrue(form.fields["user"].disabled)
        self.assertTrue(form.fields["role"].disabled)
        self.assertTrue(form.fields["is_active"].disabled)

    def test_membership_admin_cannot_delete_owner_membership(self):
        from django.contrib import admin

        membership_admin = admin.site._registry[Membership]
        self.assertFalse(
            membership_admin.has_delete_permission(None, self.owner_membership)
        )

    def test_membership_admin_allows_delete_permission_for_non_owner(self):
        from django.contrib import admin
        from types import SimpleNamespace

        member = Membership.objects.create(
            workspace=self.workspace,
            user=self.viewer,
            role=Membership.ROLE_VIEWER,
        )
        membership_admin = admin.site._registry[Membership]
        request = SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda permission: True)
        )
        self.assertTrue(membership_admin.has_delete_permission(request, member))

    def test_owner_can_update_workspace_name_but_owner_field_is_not_writable(self):
        self.authenticate(self.owner)
        response = self.client.patch(
            "/api/workspaces/current/",
            {"name": "Renamed Workspace", "owner": self.viewer.id},
            **self.workspace_headers(), format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Renamed Workspace")
        self.assertEqual(self.workspace.owner_id, self.owner.id)

    def test_manager_cannot_update_workspace(self):
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        self.authenticate(self.manager)
        response = self.client.patch(
            "/api/workspaces/current/", {"name": "Should Not Change"}, **self.workspace_headers(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_archive_workspace_and_it_disappears_from_current_context(self):
        self.authenticate(self.owner)
        response = self.client.post("/api/workspaces/current/archive/", **self.workspace_headers())
        self.assertEqual(response.status_code, 200)

        self.workspace.refresh_from_db()
        self.assertFalse(self.workspace.is_active)
        current = self.client.get("/api/workspaces/current/", **self.workspace_headers())
        self.assertEqual(current.status_code, 403)

        listing = self.client.get("/api/workspaces/")
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(self.workspace.id, [item["id"] for item in listing.data["data"]])

    def test_admin_cannot_archive_workspace(self):
        Membership.objects.create(workspace=self.workspace, user=self.admin, role=Membership.ROLE_ADMIN)
        self.authenticate(self.admin)
        response = self.client.post("/api/workspaces/current/archive/", **self.workspace_headers())
        self.assertEqual(response.status_code, 400)
        self.workspace.refresh_from_db()
        self.assertTrue(self.workspace.is_active)
