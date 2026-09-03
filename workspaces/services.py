from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Membership
from .permissions import ROLE_RANK

User = get_user_model()


def _ensure_manager_can_manage(actor_membership, target_membership=None, target_role=None):
    if ROLE_RANK[actor_membership.role] < ROLE_RANK["admin"]:
        raise ValidationError("Workspace admin permission required")

    if target_membership and target_membership.role == Membership.ROLE_OWNER:
        raise ValidationError("Workspace owner cannot be modified")

    if target_role == Membership.ROLE_OWNER:
        raise ValidationError("Owner role cannot be assigned")


def list_members(workspace):
    return Membership.objects.filter(
        workspace=workspace,
        user__is_active_account=True,
    ).select_related("user").order_by("created_at", "id")


@transaction.atomic
def add_member(workspace, actor_membership, email, role=Membership.ROLE_STAFF):
    _ensure_manager_can_manage(actor_membership, target_role=role)

    email = (email or "").strip().lower()
    if not email:
        raise ValidationError("Email is required")
    if role not in {
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
        Membership.ROLE_STAFF,
    }:
        raise ValidationError("Invalid membership role")

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        raise ValidationError("User account not found")

    if not user.is_active_account or not user.is_active:
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
    try:
        target = Membership.objects.select_for_update().get(
            workspace=workspace,
            user_id=target_user_id,
        )
    except Membership.DoesNotExist:
        raise ValidationError("Workspace member not found")

    _ensure_manager_can_manage(actor_membership, target_membership=target, target_role=role)
    if role not in {
        Membership.ROLE_ADMIN,
        Membership.ROLE_MANAGER,
        Membership.ROLE_STAFF,
    }:
        raise ValidationError("Invalid membership role")
    if not target.is_active:
        raise ValidationError("Workspace member is inactive")

    target.role = role
    target.save(update_fields=["role", "updated_at"])
    return target


@transaction.atomic
def deactivate_member(workspace, actor_membership, target_user_id):
    try:
        target = Membership.objects.select_for_update().get(
            workspace=workspace,
            user_id=target_user_id,
        )
    except Membership.DoesNotExist:
        raise ValidationError("Workspace member not found")

    _ensure_manager_can_manage(actor_membership, target_membership=target)
    if not target.is_active:
        return target

    target.is_active = False
    target.save(update_fields=["is_active", "updated_at"])
    return target
