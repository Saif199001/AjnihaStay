from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q


_MEMBERSHIP_MUTATION_ALLOWED = ContextVar(
    "membership_mutation_allowed",
    default=False,
)


@contextmanager
def _allow_membership_mutation():
    token = _MEMBERSHIP_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _MEMBERSHIP_MUTATION_ALLOWED.reset(token)


class Workspace(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_workspaces",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["owner", "is_active"])]

    def __str__(self):
        return self.name


class MembershipQuerySet(models.QuerySet):
    PROTECTED_FIELDS = frozenset({"workspace", "workspace_id", "user", "user_id", "role", "is_active"})

    def _ensure_mutation_allowed(self):
        if not _MEMBERSHIP_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Membership state must be changed through the canonical workspace service."
            )

    def update(self, **kwargs):
        if self.PROTECTED_FIELDS.intersection(kwargs):
            self._ensure_mutation_allowed()
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if self.PROTECTED_FIELDS.intersection(fields):
            self._ensure_mutation_allowed()
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        if objs:
            self._ensure_mutation_allowed()
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
        )

    def delete(self):
        self._ensure_mutation_allowed()
        return super().delete()


class Membership(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MANAGER = "manager"
    ROLE_VIEWER = "viewer"

    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_VIEWER, "Viewer"),
    )

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                name="unique_workspace_membership",
            ),
            models.UniqueConstraint(
                fields=["workspace"],
                condition=Q(role="owner", is_active=True),
                name="unique_active_workspace_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not _MEMBERSHIP_MUTATION_ALLOWED.get():
                raise PermissionDenied(
                    "Membership state must be changed through the canonical workspace service."
                )
        elif not _MEMBERSHIP_MUTATION_ALLOWED.get():
            update_fields = kwargs.get("update_fields")
            protected_fields = {"workspace", "user", "role", "is_active"}
            if update_fields is None:
                changed_fields = protected_fields
            else:
                changed_fields = protected_fields.intersection(update_fields)
            if changed_fields:
                raise PermissionDenied(
                    "Membership state must be changed through the canonical workspace service."
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _MEMBERSHIP_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Membership state must be changed through the canonical workspace service."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} @ {self.workspace.name} ({self.role})"
