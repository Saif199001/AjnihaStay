from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Membership, Workspace
from .permissions import ROLE_RANK

User = get_user_model()


def _ensure_workspace_active(workspace):
    if not workspace.is_active:
        raise ValidationError("Workspace is archived")


def _ensure_actor_membership_matches_workspace(workspace, actor_membership):
    if actor_membership is None or actor_membership.workspace_id != workspace.id:
        raise ValidationError("Workspace membership mismatch")


def _ensure_admin_can_manage(workspace, actor_membership, target_membership=None, target_role=None):
    _ensure_actor_membership_matches_workspace(workspace, actor_membership)
    if ROLE_RANK[actor_membership.role] < ROLE_RANK[Membership.ROLE_ADMIN]:
        raise ValidationError("Workspace admin permission required")

    if target_membership and target_membership.role == Membership.ROLE_OWNER:
        raise ValidationError("Workspace owner cannot be modified")

    if target_role == Membership.ROLE_OWNER:
        raise ValidationError("Owner role cannot be assigned")


def list_members(workspace):
    return Membership.objects.filter(
        workspace=workspace,
        user__is_active=True,
    ).select_related("user").order_by("created_at", "id")


@transaction.atomic
def add_member(workspace, actor_membership, email, role=Membership.ROLE_VIEWER):
    _ensure_workspace_active(workspace)
    _ensure_admin_can_manage(workspace, actor_membership, target_role=role)

    email = (email or "").strip().lower()
    if not email:
        raise ValidationError("Email is required")
    if role not in {
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
        Membership.ROLE_VIEWER,
    }:
        raise ValidationError("Invalid membership role")

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        raise ValidationError("User account not found")

    if not user.is_active:
        raise ValidationError("User account is inactive")

    membership = Membership.objects.filter(workspace=workspace, user=user).first()
    if membership:
        if membership.is_active:
            raise ValidationError("User is already an active workspace member")
        membership.role = role
        membership.is_active = True
        membership.save(update_fields=["role", "is_active", "updated_at"])
        return membership

    return Membership.objects.create(workspace=workspace, user=user, role=role)


@transaction.atomic
def change_member_role(workspace, actor_membership, target_user_id, role):
    _ensure_workspace_active(workspace)
    try:
        target = Membership.objects.select_for_update().get(
            workspace=workspace,
            user_id=target_user_id,
        )
    except Membership.DoesNotExist:
        raise ValidationError("Workspace member not found")

    _ensure_admin_can_manage(workspace, actor_membership, target_membership=target, target_role=role)
    if role not in {
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
        Membership.ROLE_VIEWER,
    }:
        raise ValidationError("Invalid membership role")
    if not target.is_active:
        raise ValidationError("Workspace member is inactive")

    target.role = role
    target.save(update_fields=["role", "updated_at"])
    return target


@transaction.atomic
def deactivate_member(workspace, actor_membership, target_user_id):
    _ensure_workspace_active(workspace)
    try:
        target = Membership.objects.select_for_update().get(
            workspace=workspace,
            user_id=target_user_id,
        )
    except Membership.DoesNotExist:
        raise ValidationError("Workspace member not found")

    _ensure_admin_can_manage(workspace, actor_membership, target_membership=target)
    if not target.is_active:
        return target

    target.is_active = False
    target.save(update_fields=["is_active", "updated_at"])
    return target


@transaction.atomic
def transfer_workspace_ownership(workspace, actor_membership, target_user_id):
    _ensure_actor_membership_matches_workspace(workspace, actor_membership)
    if actor_membership.workspace_id != workspace.id:
        raise ValidationError("Workspace membership mismatch")
    if actor_membership.role != Membership.ROLE_OWNER:
        raise ValidationError("Workspace owner permission required")
    if not workspace.is_active:
        raise ValidationError("Workspace is archived")

    workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
    current_owner = Membership.objects.select_for_update().get(
        workspace=workspace,
        user_id=workspace.owner_id,
    )

    if not current_owner.is_active or current_owner.role != Membership.ROLE_OWNER:
        raise ValidationError("Workspace owner membership is inconsistent")
    if int(target_user_id) == workspace.owner_id:
        raise ValidationError("Target user is already the workspace owner")

    try:
        target = Membership.objects.select_for_update().get(
            workspace=workspace,
            user_id=target_user_id,
        )
    except Membership.DoesNotExist:
        raise ValidationError("Target user must be an active workspace member")

    if not target.is_active:
        raise ValidationError("Target user must be an active workspace member")
    if not target.user.is_active:
        raise ValidationError("Target user account is inactive")

    current_owner.role = Membership.ROLE_ADMIN
    current_owner.save(update_fields=["role", "updated_at"])

    target.role = Membership.ROLE_OWNER
    target.save(update_fields=["role", "updated_at"])

    workspace.owner_id = target.user_id
    workspace.save(update_fields=["owner", "updated_at"])

    return workspace


@transaction.atomic
def archive_workspace(workspace, actor_membership):
    _ensure_actor_membership_matches_workspace(workspace, actor_membership)
    if actor_membership.workspace_id != workspace.id:
        raise ValidationError("Workspace membership mismatch")
    if actor_membership.role != Membership.ROLE_OWNER:
        raise ValidationError("Workspace owner permission required")

    workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
    if not workspace.is_active:
        return workspace

    workspace.is_active = False
    workspace.save(update_fields=["is_active", "updated_at"])
    return workspace
