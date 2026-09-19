from django.db import IntegrityError, transaction
from django.test import TransactionTestCase

from accounts.models import User

from .models import Membership, Workspace


class WorkspaceOwnerInvariantTests(TransactionTestCase):
    reset_sequences = True

    def make_user(self, email):
        return User.objects.create_user(email, "StrongPass123!")

    def make_valid_workspace(self, slug="owner-invariant"):
        owner = self.make_user(f"{slug}@example.com")
        with transaction.atomic():
            workspace = Workspace.objects.create(
                name="Workspace",
                slug=slug,
                owner=owner,
            )
            membership = Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=Membership.ROLE_OWNER,
                is_active=True,
            )
        return owner, workspace, membership

    def test_valid_workspace_and_owner_membership_commit(self):
        owner, workspace, membership = self.make_valid_workspace()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_workspace_cannot_commit_without_matching_owner_membership(self):
        owner = self.make_user("missing-membership@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Workspace.objects.create(
                    name="Invalid Workspace",
                    slug="missing-membership",
                    owner=owner,
                )

    def test_workspace_owner_change_requires_matching_owner_membership(self):
        owner, workspace, owner_membership = self.make_valid_workspace(
            slug="owner-change"
        )
        new_owner = self.make_user("new-owner@example.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                workspace.owner = new_owner
                workspace.save(update_fields=["owner", "updated_at"])

        workspace.refresh_from_db()
        owner_membership.refresh_from_db()
        self.assertEqual(workspace.owner_id, owner.id)
        self.assertEqual(owner_membership.role, Membership.ROLE_OWNER)
        self.assertTrue(owner_membership.is_active)

    def test_owner_membership_cannot_be_deactivated_when_it_is_the_only_owner(self):
        owner, workspace, membership = self.make_valid_workspace(
            slug="owner-deactivate"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                membership.is_active = False
                membership.save(update_fields=["is_active", "updated_at"])

        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.role, Membership.ROLE_OWNER)

    def test_owner_membership_cannot_be_demoted_when_it_is_the_only_owner(self):
        owner, workspace, membership = self.make_valid_workspace(
            slug="owner-demote"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                membership.role = Membership.ROLE_ADMIN
                membership.save(update_fields=["role", "updated_at"])

        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.ROLE_OWNER)
        self.assertTrue(membership.is_active)

    def test_only_one_active_owner_membership_is_allowed(self):
        owner, workspace, membership = self.make_valid_workspace(
            slug="single-owner"
        )
        second_user = self.make_user("second-owner@example.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    workspace=workspace,
                    user=second_user,
                    role=Membership.ROLE_OWNER,
                    is_active=True,
                )

        self.assertEqual(
            Membership.objects.filter(
                workspace=workspace,
                role=Membership.ROLE_OWNER,
                is_active=True,
            ).count(),
            1,
        )
        self.assertEqual(
            Membership.objects.get(
                workspace=workspace,
                role=Membership.ROLE_OWNER,
                is_active=True,
            ).user_id,
            owner.id,
        )

    def test_workspace_owner_and_membership_can_be_transferred_atomically(self):
        owner, workspace, owner_membership = self.make_valid_workspace(
            slug="owner-transfer-db"
        )
        target = self.make_user("transfer-target@example.com")
        target_membership = Membership.objects.create(
            workspace=workspace,
            user=target,
            role=Membership.ROLE_MANAGER,
            is_active=True,
        )

        from .services import transfer_workspace_ownership

        transfer_workspace_ownership(workspace, owner_membership, target.id)

        workspace.refresh_from_db()
        owner_membership.refresh_from_db()
        target_membership.refresh_from_db()

        self.assertEqual(workspace.owner_id, target.id)
        self.assertEqual(owner_membership.role, Membership.ROLE_ADMIN)
        self.assertTrue(owner_membership.is_active)
        self.assertEqual(target_membership.role, Membership.ROLE_OWNER)
        self.assertTrue(target_membership.is_active)
