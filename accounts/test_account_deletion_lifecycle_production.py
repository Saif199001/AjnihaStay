from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from .admin import UserAdmin
from .services import set_account_active


User = get_user_model()


class AccountDeletionLifecycleBoundaryProductionTests(TestCase):
    def setUp(self):
        self.admin = UserAdmin(User, None)
        self.user = User.objects.create_user(
            email="deletion-target@example.com",
            password="StrongPass123!",
            email_verified=True,
        )

    def create_owned_workspace(self, owner, *, name, slug):
        from workspaces.models import Membership, Workspace, _allow_membership_mutation

        workspace = Workspace.objects.create(
            name=name,
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

    def test_direct_instance_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.user.delete()

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_queryset_delete_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            User.objects.filter(pk=self.user.pk).delete()

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_admin_delete_is_disabled(self):
        self.assertFalse(
            self.admin.has_delete_permission(
                type("Request", (), {"user": self.user})(),
                self.user,
            )
        )

    def test_canonical_deactivation_remains_available(self):
        locked_user = set_account_active(self.user, False)

        self.assertFalse(locked_user.is_active)
        self.assertFalse(User.objects.get(pk=self.user.pk).is_active)

    def test_deactivation_does_not_delete_memberships(self):
        from workspaces.models import Membership, _allow_membership_mutation

        owner = User.objects.create_user(
            email="workspace-owner@example.com",
            password="StrongPass123!",
            email_verified=True,
        )
        workspace = self.create_owned_workspace(
            owner,
            name="Lifecycle Workspace",
            slug="lifecycle-workspace",
        )
        with _allow_membership_mutation():
            membership = Membership.objects.create(
                workspace=workspace,
                user=self.user,
                role=Membership.ROLE_VIEWER,
                is_active=True,
            )

        set_account_active(self.user, False)

        self.assertTrue(
            Membership.objects.filter(pk=membership.pk).exists()
        )
        self.assertFalse(Membership.objects.get(pk=membership.pk).user.is_active)

    def test_owner_hard_delete_remains_protected_by_workspace_relation(self):
        owner = User.objects.create_user(
            email="protected-owner@example.com",
            password="StrongPass123!",
            email_verified=True,
        )
        workspace = self.create_owned_workspace(
            owner,
            name="Protected Workspace",
            slug="protected-workspace",
        )

        with self.assertRaises(PermissionDenied):
            owner.delete()

        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        self.assertTrue(
            workspace.__class__.objects.filter(pk=workspace.pk).exists()
        )
