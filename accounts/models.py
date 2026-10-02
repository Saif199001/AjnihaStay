from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


_ACCOUNT_STATE_MUTATION_ALLOWED = ContextVar(
    "account_state_mutation_allowed",
    default=False,
)


@contextmanager
def _allow_account_state_mutation():
    token = _ACCOUNT_STATE_MUTATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _ACCOUNT_STATE_MUTATION_ALLOWED.reset(token)


class UserQuerySet(models.QuerySet):
    SENSITIVE_STATE_FIELDS = frozenset(
        {"is_active", "email_verified", "email_verified_at"}
    )

    def _ensure_sensitive_state_mutation_allowed(self, fields):
        sensitive_fields = self.SENSITIVE_STATE_FIELDS.intersection(fields)
        if sensitive_fields and not _ACCOUNT_STATE_MUTATION_ALLOWED.get():
            raise PermissionDenied(
                "Sensitive account state must be changed through the canonical "
                "accounts service."
            )

    def update(self, **kwargs):
        self._ensure_sensitive_state_mutation_allowed(kwargs.keys())
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        self._ensure_sensitive_state_mutation_allowed(fields)
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def delete(self):
        raise PermissionDenied(
            "Account deletion must use the canonical account lifecycle."
        )


class UserManager(BaseUserManager):
    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = email.strip().lower()
        extra_fields.setdefault("email_verified", False)
        extra_fields.setdefault("email_verified_at", None)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields["email_verified"] = True
        extra_fields["email_verified_at"] = timezone.now()

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    SENSITIVE_STATE_FIELDS = frozenset(
        {"is_active", "email_verified", "email_verified_at"}
    )

    def save(self, *args, **kwargs):
        if not self._state.adding and not _ACCOUNT_STATE_MUTATION_ALLOWED.get():
            update_fields = kwargs.get("update_fields")

            if update_fields is None:
                fields_to_check = self.SENSITIVE_STATE_FIELDS
            else:
                fields_to_check = self.SENSITIVE_STATE_FIELDS.intersection(
                    update_fields
                )

            if fields_to_check:
                current = type(self).objects.get(pk=self.pk)

                changed_sensitive_fields = {
                    field
                    for field in fields_to_check
                    if getattr(current, field) != getattr(self, field)
                }

                if changed_sensitive_fields:
                    raise PermissionDenied(
                        "Sensitive account state must be changed through the "
                        "canonical accounts service."
                    )

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            "Account deletion must use the canonical account lifecycle."
        )


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    profile_pic = models.ImageField(upload_to="profiles/", blank=True, null=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.email
