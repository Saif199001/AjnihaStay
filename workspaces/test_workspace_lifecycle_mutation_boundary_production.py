from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.test import TestCase

from rest_framework.exceptions import PermissionDenied

from .models import Membership, Workspace, _allow_membership_mutation
from .services import (
    archive_workspace,
    change_member_role,
    transfer_workspace_ownership,
    update_workspace,
)

User = get_user_model()


class WorkspaceLifecycleMutationBoundaryProductionTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"

    def create_user(self, email):
        return User.objects.create_user(
            email=email,
            password=self.password,
            email_verified=True,
            is_active=True,
        )

    def create_workspace(self, owner, slug):
        workspace = Workspace.objects.create(
            name="Test Workspace",
            slug=slug,
            owner=owner,
        )
        with _allow_membership_mutation():
            Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=Membership.ROLE_OWNER,
                is_active=True,
            )
        return workspace

    def create_membership(self, workspace, user, role):
        with _allow_membership_mutation():
            return Membership.objects.create(
                workspace=workspace,
                user=user,
                role=role,
                is_active=True,
            )

    def test_direct_save_lifecycle_fields_is_blocked(self):
        owner = self.create_user("owner-save@example.com")
        workspace = self.create_workspace(owner, "direct-save")

        workspace.is_active = False

        with self.assertRaises(DjangoPermissionDenied):
            workspace.save()

    def test_direct_queryset_update_lifecycle_fields_is_blocked(self):
        owner = self.create_user("owner-update@example.com")
        workspace = self.create_workspace(owner, "direct-update")

        with self.assertRaises(DjangoPermissionDenied):
            Workspace.objects.filter(pk=workspace.pk).update(is_active=False)

    def test_direct_bulk_update_lifecycle_fields_is_blocked(self):
        owner = self.create_user("owner-bulk@example.com")
        workspace = self.create_workspace(owner, "direct-bulk")

        workspace.name = "Changed"

        with self.assertRaises(DjangoPermissionDenied):
            Workspace.objects.bulk_update([workspace], ["name"])

    def test_direct_delete_is_blocked(self):
        owner = self.create_user("owner-delete@example.com")
        workspace = self.create_workspace(owner, "direct-delete")

        with self.assertRaises(DjangoPermissionDenied):
            workspace.delete()

    def test_queryset_delete_is_blocked(self):
        owner = self.create_user("owner-query-delete@example.com")
        workspace = self.create_workspace(owner, "query-delete")

        with self.assertRaises(DjangoPermissionDenied):
            Workspace.objects.filter(pk=workspace.pk).delete()

    def test_update_workspace_uses_fresh_actor_membership(self):
        owner = self.create_user("owner-fresh-update@example.com")
        admin = self.create_user("admin-fresh-update@example.com")
        workspace = self.create_workspace(owner, "fresh-update")
        admin_membership = self.create_membership(
            workspace,
            admin,
            Membership.ROLE_ADMIN,
        )

        change_member_role(
            workspace,
            workspace.memberships.get(user=owner),
            admin.id,
            Membership.ROLE_MANAGER,
        )

        with self.assertRaises(PermissionDenied):
            update_workspace(
                workspace,
                admin_membership,
                "Should Not Update",
            )

        workspace.refresh_from_db()
        self.assertEqual(workspace.name, "Test Workspace")

    def test_archive_workspace_uses_fresh_actor_membership(self):
        owner = self.create_user("owner-fresh-archive@example.com")
        target = self.create_user("target-fresh-archive@example.com")
        workspace = self.create_workspace(owner, "fresh-archive")
        self.create_membership(
            workspace,
            target,
            Membership.ROLE_VIEWER,
        )

        stale_owner_membership = workspace.memberships.get(user=owner)

        transfer_workspace_ownership(
            workspace,
            stale_owner_membership,
            target.id,
        )

        with self.assertRaises(PermissionDenied):
            archive_workspace(workspace, stale_owner_membership)

        workspace.refresh_from_db()
        self.assertTrue(workspace.is_active)

    def test_update_workspace_valid_service_mutation_succeeds(self):
        owner = self.create_user("owner-valid-update@example.com")
        workspace = self.create_workspace(owner, "valid-update")

        update_workspace(
            workspace,
            workspace.memberships.get(user=owner),
            "Updated Workspace",
        )

        workspace.refresh_from_db()
        self.assertEqual(workspace.name, "Updated Workspace")

    def test_archive_workspace_valid_owner_succeeds(self):
        owner = self.create_user("owner-valid-archive@example.com")
        workspace = self.create_workspace(owner, "valid-archive")

        archive_workspace(
            workspace,
            workspace.memberships.get(user=owner),
        )

        workspace.refresh_from_db()
        self.assertFalse(workspace.is_active)

    def test_ownership_transfer_remains_supported(self):
        owner = self.create_user("owner-transfer@example.com")
        target = self.create_user("target-transfer@example.com")
        workspace = self.create_workspace(owner, "valid-transfer")
        self.create_membership(
            workspace,
            target,
            Membership.ROLE_VIEWER,
        )

        transfer_workspace_ownership(
            workspace,
            workspace.memberships.get(user=owner),
            target.id,
        )

        workspace.refresh_from_db()
        self.assertEqual(workspace.owner_id, target.id)
        self.assertEqual(
            workspace.memberships.get(user=target).role,
            Membership.ROLE_OWNER,
        )
        self.assertEqual(
            workspace.memberships.get(user=owner).role,
            Membership.ROLE_ADMIN,
        )

    def test_workspace_admin_lifecycle_mutations_are_disabled(self):
        from .admin import WorkspaceAdmin

        admin_instance = WorkspaceAdmin(Workspace, None)

        class Request:
            pass

        request = Request()

        self.assertFalse(admin_instance.has_add_permission(request))
        self.assertFalse(admin_instance.has_change_permission(request))
        self.assertFalse(admin_instance.has_delete_permission(request))
