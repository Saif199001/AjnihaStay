from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import TransactionTestCase

from .models import Membership, Workspace, _allow_membership_mutation
from .services import add_member, change_member_role, deactivate_member

User = get_user_model()


class MembershipMutationBoundaryProductionTests(TransactionTestCase):
    reset_sequences = True

    def create_user(self, email):
        return User.objects.create_user(
            email=email,
            password="StrongPass123!",
            email_verified=True,
        )

    def create_owned_workspace(self, owner, slug="workspace"):
        with transaction.atomic():
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

    def create_membership(self, workspace, user, role=Membership.ROLE_VIEWER, is_active=True):
        with _allow_membership_mutation():
            return Membership.objects.create(
                workspace=workspace,
                user=user,
                role=role,
                is_active=is_active,
            )

    def test_direct_create_is_blocked(self):
        owner = self.create_user("owner@example.com")
        workspace = self.create_owned_workspace(owner, "direct-create")
        member = self.create_user("member@example.com")

        with self.assertRaises(PermissionDenied):
            Membership.objects.create(
                workspace=workspace,
                user=member,
                role=Membership.ROLE_VIEWER,
                is_active=True,
            )

    def test_direct_save_role_change_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "direct-role")
        membership = self.create_membership(workspace, member)

        membership.role = Membership.ROLE_ADMIN
        with self.assertRaises(PermissionDenied):
            membership.save(update_fields=["role"])

        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.ROLE_VIEWER)

    def test_direct_save_active_state_change_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "direct-active")
        membership = self.create_membership(workspace, member)

        membership.is_active = False
        with self.assertRaises(PermissionDenied):
            membership.save(update_fields=["is_active"])

        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_direct_save_workspace_reassignment_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace_a = self.create_owned_workspace(owner, "workspace-a")
        owner_b = self.create_user("owner-b@example.com")
        workspace_b = self.create_owned_workspace(owner_b, "workspace-b")
        membership = self.create_membership(workspace_a, member)

        membership.workspace = workspace_b
        with self.assertRaises(PermissionDenied):
            membership.save(update_fields=["workspace"])

        membership.refresh_from_db()
        self.assertEqual(membership.workspace_id, workspace_a.id)

    def test_direct_save_user_reassignment_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        other = self.create_user("other@example.com")
        workspace = self.create_owned_workspace(owner, "user-reassignment")
        membership = self.create_membership(workspace, member)

        membership.user = other
        with self.assertRaises(PermissionDenied):
            membership.save(update_fields=["user"])

        membership.refresh_from_db()
        self.assertEqual(membership.user_id, member.id)

    def test_queryset_update_protected_fields_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "queryset-update")
        membership = self.create_membership(workspace, member)

        with self.assertRaises(PermissionDenied):
            Membership.objects.filter(pk=membership.pk).update(
                role=Membership.ROLE_ADMIN,
                is_active=False,
            )

        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.ROLE_VIEWER)
        self.assertTrue(membership.is_active)

    def test_bulk_update_protected_fields_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "bulk-update")
        membership = self.create_membership(workspace, member)

        membership.role = Membership.ROLE_ADMIN
        with self.assertRaises(PermissionDenied):
            Membership.objects.bulk_update([membership], ["role"])

        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.ROLE_VIEWER)

    def test_bulk_create_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "bulk-create")

        candidate = Membership(
            workspace=workspace,
            user=member,
            role=Membership.ROLE_VIEWER,
            is_active=True,
        )
        with self.assertRaises(PermissionDenied):
            Membership.objects.bulk_create([candidate])

    def test_queryset_delete_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "queryset-delete")
        membership = self.create_membership(workspace, member)

        with self.assertRaises(PermissionDenied):
            Membership.objects.filter(pk=membership.pk).delete()

        self.assertTrue(Membership.objects.filter(pk=membership.pk).exists())

    def test_instance_delete_is_blocked(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "instance-delete")
        membership = self.create_membership(workspace, member)

        with self.assertRaises(PermissionDenied):
            membership.delete()

        self.assertTrue(Membership.objects.filter(pk=membership.pk).exists())

    def test_add_member_service_creates_membership(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "service-add")
        actor = Membership.objects.get(workspace=workspace, user=owner)

        membership = add_member(
            workspace,
            actor,
            member.email,
            Membership.ROLE_MANAGER,
        )

        self.assertEqual(membership.role, Membership.ROLE_MANAGER)
        self.assertTrue(membership.is_active)

    def test_change_member_role_service_mutates_membership(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "service-role")
        target = self.create_membership(workspace, member)
        actor = Membership.objects.get(workspace=workspace, user=owner)

        changed = change_member_role(
            workspace,
            actor,
            member.id,
            Membership.ROLE_ADMIN,
        )

        self.assertEqual(changed.pk, target.pk)
        target.refresh_from_db()
        self.assertEqual(target.role, Membership.ROLE_ADMIN)

    def test_deactivate_member_service_mutates_membership(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "service-deactivate")
        target = self.create_membership(workspace, member)
        actor = Membership.objects.get(workspace=workspace, user=owner)

        deactivated = deactivate_member(workspace, actor, member.id)

        self.assertEqual(deactivated.pk, target.pk)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_owner_role_cannot_be_assigned_by_member_service(self):
        owner = self.create_user("owner@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "service-owner-role")
        self.create_membership(workspace, member)
        actor = Membership.objects.get(workspace=workspace, user=owner)

        with self.assertRaisesMessage(PermissionDenied, "Workspace admin permission required"):
            add_member(
                workspace,
                actor,
                member.email,
                Membership.ROLE_OWNER,
            )

    def test_stale_admin_actor_cannot_mutate_after_role_downgrade(self):
        owner = self.create_user("owner@example.com")
        admin = self.create_user("admin@example.com")
        member = self.create_user("member@example.com")
        workspace = self.create_owned_workspace(owner, "stale-admin")
        admin_membership = self.create_membership(
            workspace,
            admin,
            Membership.ROLE_ADMIN,
        )
        self.create_membership(workspace, member)

        with _allow_membership_mutation():
            Membership.objects.filter(pk=admin_membership.pk).update(
                role=Membership.ROLE_VIEWER
            )

        with self.assertRaises(PermissionDenied):
            change_member_role(
                workspace,
                admin_membership,
                member.id,
                Membership.ROLE_MANAGER,
            )

    def test_w1_owner_transfer_path_remains_allowed(self):
        from .services import transfer_workspace_ownership

        owner = self.create_user("owner@example.com")
        target = self.create_user("target@example.com")
        workspace = self.create_owned_workspace(owner, "w1-regression")
        self.create_membership(workspace, target)

        actor = Membership.objects.get(workspace=workspace, user=owner)
        transfer_workspace_ownership(workspace, actor, target.id)

        workspace.refresh_from_db()
        self.assertEqual(workspace.owner_id, target.id)
        self.assertEqual(
            Membership.objects.get(workspace=workspace, user=target).role,
            Membership.ROLE_OWNER,
        )
