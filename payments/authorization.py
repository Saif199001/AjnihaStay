from django.core.exceptions import PermissionDenied

from workspaces.models import Membership


MUTATION_ROLES = {
    Membership.ROLE_OWNER,
    Membership.ROLE_ADMIN,
    Membership.ROLE_MANAGER,
}


def require_mutation_permission(user, workspace):
    """Require an active Owner/Admin/Manager membership for financial mutations."""
    if user is None:
        raise PermissionDenied("Financial mutation requires workspace membership")

    allowed = Membership.objects.filter(
        workspace=workspace,
        user=user,
        is_active=True,
        role__in=MUTATION_ROLES,
    ).exists()
    if not allowed:
        raise PermissionDenied("Financial mutation requires manager-level access")
