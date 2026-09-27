from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from .models import Membership, Workspace, _allow_membership_mutation
from .services import transfer_workspace_ownership

User = get_user_model()


class WorkspaceOwnerInvariantProductionTests(TransactionTestCase):
    reset_sequences = True

    def create_user(self, email):
        return User.objects.create_user(
            email=email,
            password="StrongPass123!",
            email_verified=True,
        )


    def create_membership(self, workspace, user, role, is_active=True):
        with _allow_membership_mutation():
            return self.create_membership(
                workspace=workspace,
                user=user,
                role=role,
                is_active=is_active,
            )

    def create_owned_workspace(self, owner, slug="workspace"):
        with transaction.atomic():
            workspace = Workspace.objects.create(
                name="Test Workspace",
                slug=slug,
                owner=owner,
            )
            Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=Membership.ROLE_OWNER,
                is_active=True,
            )
        return workspace

    def test_valid_workspace_and_owner_membership_can_commit(self):
        owner = self.create_user("owner@example.com")

        with transaction.atomic():
            workspace = Workspace.objects.create(
                name="Valid Workspace",
                slug="valid-workspace",
                owner=owner,
            )
            Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=Membership.ROLE_OWNER,
                is_active=True,
            )

        self.assertEqual(
            Workspace.objects.get(pk=workspace.pk).owner_id,
            owner.id,
        )

    def test_workspace_without_owner_membership_cannot_commit(self):
        owner = self.create_user("owner@example.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Workspace.objects.create(
                    name="Invalid Workspace",
                    slug="invalid-workspace",
                    owner=owner,
                )

        self.assertFalse(
            Workspace.objects.filter(slug="invalid-workspace").exists()
        )

    def test_wrong_user_owner_membership_cannot_commit(self):
        owner = self.create_user("owner@example.com")
        other_user = self.create_user("other@example.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                workspace = Workspace.objects.create(
                    name="Wrong Owner Workspace",
                    slug="wrong-owner-workspace",
                    owner=owner,
                )
                Membership.objects.create(
                    workspace=workspace,
                    user=other_user,
                    role=Membership.ROLE_OWNER,
                    is_active=True,
                )

        self.assertFalse(
            Workspace.objects.filter(slug="wrong-owner-workspace").exists()
        )

    def test_two_active_owner_memberships_cannot_exist(self):
        owner = self.create_user("owner@example.com")
        second_user = self.create_user("second@example.com")
        workspace = self.create_owned_workspace(owner, "two-owner-workspace")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    workspace=workspace,
                    user=second_user,
                    role=Membership.ROLE_OWNER,
                    is_active=True,
                )

    def test_owner_membership_cannot_be_deactivated_directly(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "deactivate-owner")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.filter(
                    workspace=workspace,
                    user=owner,
                ).update(is_active=False)

    def test_owner_membership_cannot_be_deleted_directly(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "delete-owner")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.filter(
                    workspace=workspace,
                    user=owner,
                ).delete()

    def test_owner_role_cannot_be_changed_directly(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "change-owner-role")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.filter(
                    workspace=workspace,
                    user=owner,
                ).update(role=Membership.ROLE_ADMIN)

    def test_workspace_owner_cannot_change_to_inconsistent_user(self):
        owner = self.create_user("owner@example.com")
        other_user = self.create_user("other@example.com")
        workspace = self.create_owned_workspace(owner, "change-workspace-owner")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Workspace.objects.filter(pk=workspace.pk).update(
                    owner_id=other_user.id
                )

    def test_valid_ownership_transfer_preserves_invariant(self):
        owner = self.create_user("owner@example.com")
        target = self.create_user("target@example.com")
        workspace = self.create_owned_workspace(owner, "transfer-owner")

        Membership.objects.create(
            workspace=workspace,
            user=target,
            role=Membership.ROLE_VIEWER,
            is_active=True,
        )

        actor = Membership.objects.get(
            workspace=workspace,
            user=owner,
        )

        transfer_workspace_ownership(workspace, actor, target.id)

        workspace.refresh_from_db()
        old_owner = Membership.objects.get(workspace=workspace, user=owner)
        new_owner = Membership.objects.get(workspace=workspace, user=target)

        self.assertEqual(workspace.owner_id, target.id)
        self.assertEqual(old_owner.role, Membership.ROLE_ADMIN)
        self.assertEqual(new_owner.role, Membership.ROLE_OWNER)
        self.assertTrue(new_owner.is_active)

    def test_stale_non_owner_actor_cannot_transfer_again(self):
        owner = self.create_user("owner@example.com")
        target = self.create_user("target@example.com")
        third_user = self.create_user("third@example.com")
        workspace = self.create_owned_workspace(owner, "stale-owner")

        Membership.objects.create(
            workspace=workspace,
            user=target,
            role=Membership.ROLE_VIEWER,
            is_active=True,
        )
        Membership.objects.create(
            workspace=workspace,
            user=third_user,
            role=Membership.ROLE_VIEWER,
            is_active=True,
        )

        stale_owner_membership = Membership.objects.get(
            workspace=workspace,
            user=owner,
        )

        transfer_workspace_ownership(
            workspace,
            stale_owner_membership,
            target.id,
        )

        with self.assertRaises(ValidationError) as exc:
            transfer_workspace_ownership(
                workspace,
                stale_owner_membership,
                third_user.id,
            )

        self.assertEqual(
            exc.exception.detail,
            ["Workspace owner permission required"],
        )
