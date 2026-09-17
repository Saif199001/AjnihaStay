from django.db import connection, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from .context import get_workspace_for_request
from .db import set_workspace_context
from .models import Membership, Workspace
from .services import archive_workspace, transfer_workspace_ownership


class WorkspaceFoundationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123!"

    def make_workspace(self, email="owner@example.com", slug="workspace"):
        owner = User.objects.create_user(email, self.password)
        workspace = Workspace.objects.create(name="Workspace", slug=slug, owner=owner)
        membership = Membership.objects.create(
            workspace=workspace,
            user=owner,
            role=Membership.ROLE_OWNER,
        )
        return owner, workspace, membership

    def test_signup_creates_workspace_and_owner_membership(self):
        response = self.client.post(
            "/api/signup/",
            {
                "email": "new-owner@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "workspace_name": "New Owner Rentals",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="new-owner@example.com")
        workspace = Workspace.objects.get(owner=user)
        membership = Membership.objects.get(workspace=workspace, user=user)

        self.assertEqual(workspace.name, "New Owner Rentals")
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_workspace_owner_and_owner_membership_are_consistent(self):
        owner, workspace, membership = self.make_workspace()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(membership.user_id, workspace.owner_id)
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_membership_role_contract_is_owner_admin_manager_viewer(self):
        self.assertEqual(
            set(dict(Membership.ROLE_CHOICES)),
            {
                Membership.ROLE_OWNER,
                Membership.ROLE_ADMIN,
                Membership.ROLE_MANAGER,
                Membership.ROLE_VIEWER,
            },
        )
        self.assertNotIn("staff", dict(Membership.ROLE_CHOICES))
        self.assertEqual(Membership._meta.get_field("role").default, Membership.ROLE_VIEWER)

    def test_workspace_list_returns_only_active_memberships(self):
        user = User.objects.create_user("member@example.com", self.password)
        workspace_a = Workspace.objects.create(name="A", slug="a", owner=user)
        workspace_b = Workspace.objects.create(name="B", slug="b", owner=user)
        Membership.objects.create(workspace=workspace_a, user=user, role=Membership.ROLE_OWNER)
        Membership.objects.create(
            workspace=workspace_b, user=user, role=Membership.ROLE_VIEWER, is_active=False
        )

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [workspace_a.id])

    def test_workspace_context_rejects_workspace_without_membership(self):
        user = User.objects.create_user("member2@example.com", self.password)
        other = User.objects.create_user("other@example.com", self.password)
        workspace = Workspace.objects.create(name="Other", slug="other", owner=other)
        Membership.objects.create(workspace=workspace, user=other, role=Membership.ROLE_OWNER)

        self.client.force_authenticate(user=user)
        response = self.client.get(
            "/api/workspaces/current/", HTTP_X_WORKSPACE_ID=str(workspace.id)
        )

        self.assertEqual(response.status_code, 403)

    def test_single_membership_is_selected_without_header(self):
        user = User.objects.create_user("single@example.com", self.password)
        workspace = Workspace.objects.create(name="Single", slug="single", owner=user)
        Membership.objects.create(workspace=workspace, user=user, role=Membership.ROLE_OWNER)

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["workspace"]["id"], workspace.id)

    def test_multiple_memberships_require_explicit_workspace(self):
        user = User.objects.create_user("multi@example.com", self.password)
        workspace_a = Workspace.objects.create(name="A", slug="multi-a", owner=user)
        workspace_b = Workspace.objects.create(name="B", slug="multi-b", owner=user)
        Membership.objects.create(workspace=workspace_a, user=user, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=workspace_b, user=user, role=Membership.ROLE_ADMIN)

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/workspaces/current/")

        self.assertEqual(response.status_code, 403)

    def test_workspace_context_returns_only_callers_membership(self):
        user = User.objects.create_user("context@example.com", self.password)
        workspace = Workspace.objects.create(name="Mine", slug="mine", owner=user)
        Membership.objects.create(workspace=workspace, user=user, role=Membership.ROLE_MANAGER)

        other = User.objects.create_user("intruder@example.com", self.password)
        other_workspace = Workspace.objects.create(name="Other", slug="other-context", owner=other)
        Membership.objects.create(workspace=other_workspace, user=other, role=Membership.ROLE_OWNER)

        self.client.force_authenticate(user=user)
        request = self.client.get(
            "/api/workspaces/current/", HTTP_X_WORKSPACE_ID=str(other_workspace.id)
        ).wsgi_request

        with self.assertRaises(Exception):
            get_workspace_for_request(request)

    def test_property_is_scoped_to_workspace(self):
        owner = User.objects.create_user("property-owner@example.com", self.password)
        other = User.objects.create_user("property-other@example.com", self.password)
        workspace = Workspace.objects.create(name="Owner WS", slug="property-owner", owner=owner)
        other_workspace = Workspace.objects.create(name="Other WS", slug="property-other", owner=other)
        Membership.objects.create(workspace=workspace, user=owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=other_workspace, user=other, role=Membership.ROLE_OWNER)
        prop = Property.objects.create(
            owner=owner, workspace=workspace, name="Owner Property", property_type="pg",
            address="Delhi", city="Delhi", state="Delhi", pincode="110001",
        )

        self.assertEqual(Property.objects.filter(workspace=workspace).count(), 1)
        self.assertEqual(Property.objects.filter(workspace=other_workspace).count(), 0)
        self.assertEqual(prop.workspace_id, workspace.id)

    def test_workspace_context_sets_current_transaction(self):
        workspace = Workspace.objects.create(
            name="Context", slug="context-test",
            owner=User.objects.create_user("db-context@example.com", self.password),
        )

        with transaction.atomic():
            set_workspace_context(workspace.id)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.workspace_id', true)")
                self.assertEqual(cursor.fetchone()[0], str(workspace.id))

    def test_transfer_ownership_updates_workspace_and_memberships_atomically(self):
        owner, workspace, owner_membership = self.make_workspace()
        target = User.objects.create_user("target@example.com", self.password)
        target_membership = Membership.objects.create(
            workspace=workspace, user=target, role=Membership.ROLE_MANAGER
        )

        result = transfer_workspace_ownership(workspace, owner_membership, target.id)
        workspace.refresh_from_db()
        owner_membership.refresh_from_db()
        target_membership.refresh_from_db()

        self.assertEqual(result.owner_id, target.id)
        self.assertEqual(workspace.owner_id, target.id)
        self.assertEqual(owner_membership.role, Membership.ROLE_ADMIN)
        self.assertEqual(target_membership.role, Membership.ROLE_OWNER)
        self.assertTrue(owner_membership.is_active)
        self.assertTrue(target_membership.is_active)

    def test_transfer_rejects_cross_workspace_target_without_changes(self):
        owner, workspace, owner_membership = self.make_workspace()
        other_owner = User.objects.create_user("other-owner@example.com", self.password)
        other_workspace = Workspace.objects.create(name="Other", slug="other-ws", owner=other_owner)
        Membership.objects.create(
            workspace=other_workspace, user=other_owner, role=Membership.ROLE_OWNER
        )

        with self.assertRaises(ValidationError):
            transfer_workspace_ownership(workspace, owner_membership, other_owner.id)

        workspace.refresh_from_db()
        owner_membership.refresh_from_db()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(owner_membership.role, Membership.ROLE_OWNER)

    def test_transfer_rejects_inactive_target(self):
        owner, workspace, owner_membership = self.make_workspace()
        target = User.objects.create_user("inactive-target@example.com", self.password)
        target_membership = Membership.objects.create(
            workspace=workspace, user=target, role=Membership.ROLE_ADMIN, is_active=False
        )

        with self.assertRaises(ValidationError):
            transfer_workspace_ownership(workspace, owner_membership, target.id)

        workspace.refresh_from_db()
        target_membership.refresh_from_db()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(target_membership.role, Membership.ROLE_ADMIN)
        self.assertFalse(target_membership.is_active)

    def test_non_owner_cannot_transfer_ownership(self):
        owner, workspace, owner_membership = self.make_workspace()
        admin = User.objects.create_user("admin@example.com", self.password)
        admin_membership = Membership.objects.create(
            workspace=workspace, user=admin, role=Membership.ROLE_ADMIN
        )

        with self.assertRaises(ValidationError):
            transfer_workspace_ownership(workspace, admin_membership, owner.id)

        workspace.refresh_from_db()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(owner_membership.role, Membership.ROLE_OWNER)

    def test_archive_requires_owner_and_blocks_membership_lifecycle(self):
        owner, workspace, owner_membership = self.make_workspace(slug="archive-test")
        archive_workspace(workspace, owner_membership)
        workspace.refresh_from_db()
        self.assertFalse(workspace.is_active)

        member = User.objects.create_user("archive-member@example.com", self.password)
        member_membership = Membership.objects.create(
            workspace=workspace, user=member, role=Membership.ROLE_VIEWER
        )

        from .services import add_member, change_member_role, deactivate_member
        with self.assertRaises(ValidationError):
            add_member(workspace, owner_membership, member.email, Membership.ROLE_VIEWER)
        with self.assertRaises(ValidationError):
            change_member_role(workspace, owner_membership, member.id, Membership.ROLE_MANAGER)
        with self.assertRaises(ValidationError):
            deactivate_member(workspace, owner_membership, member.id)

        member_membership.refresh_from_db()
        self.assertTrue(member_membership.is_active)

    def test_archive_is_idempotent(self):
        owner, workspace, owner_membership = self.make_workspace(slug="archive-idempotent")
        archive_workspace(workspace, owner_membership)
        workspace.refresh_from_db()
        archived = archive_workspace(workspace, owner_membership)
        self.assertFalse(archived.is_active)
