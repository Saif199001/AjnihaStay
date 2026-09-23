import os

import resend

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.text import slugify
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

from .models import User
from workspaces.models import Membership, Workspace

User = get_user_model()


class EmailVerificationDeliveryError(Exception):
    """Expected email-delivery failure for verification messages."""


class PasswordResetDeliveryError(Exception):
    """Expected email-delivery failure for password-reset messages."""


def _unique_workspace_slug(email):
    base = slugify(email.split("@")[0]) or "workspace"
    slug = base
    counter = 2
    while Workspace.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _create_workspace_with_unique_slug(name, email, owner):
    base = slugify(email.split("@")[0]) or "workspace"
    slug = _unique_workspace_slug(email)
    counter = 2

    while True:
        try:
            with transaction.atomic():
                return Workspace.objects.create(name=name, slug=slug, owner=owner)
        except IntegrityError:
            if Workspace.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
                continue
            raise


def create_user_account(email, password, confirm_password, workspace_name=None):
    if not isinstance(email, str):
        raise ValidationError("Email is required")
    email = email.strip().lower()

    if password != confirm_password:
        raise ValidationError("Passwords do not match")

    validate_password(password)

    if User.objects.filter(email=email).exists():
        raise ValidationError("Email already exists")

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=password,
            email_verified=False,
            email_verified_at=None,
        )
        name = (workspace_name or "").strip() or f"{email}'s Workspace"
        workspace = _create_workspace_with_unique_slug(name, email, user)
        Membership.objects.create(
            workspace=workspace,
            user=user,
            role=Membership.ROLE_OWNER,
            is_active=True,
        )

    return user


def login_user_service(request, email, password):
    return authenticate(request, email=email, password=password)


def set_account_active(user, is_active):
    """Change Django's canonical account state and revoke tokens on deactivation."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)

        if locked_user.is_active == is_active:
            return locked_user

        locked_user.is_active = is_active
        locked_user.save(update_fields=["is_active"])

        if not is_active:
            for outstanding in OutstandingToken.objects.filter(user=locked_user):
                BlacklistedToken.objects.get_or_create(token=outstanding)

        return locked_user


def verify_user_email(user, token):
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)

        if locked_user.email_verified:
            return locked_user

        if not default_token_generator.check_token(locked_user, token):
            raise ValidationError("Invalid or expired verification link")

        locked_user.email_verified = True
        locked_user.email_verified_at = timezone.now()
        locked_user.save(update_fields=["email_verified", "email_verified_at"])
        return locked_user


def _send_resend_email(*, to_email, subject, html, error_type):
    if not settings.RESEND_API_KEY:
        raise error_type("Email delivery service is not configured")

    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send({
            "from": os.getenv("EMAIL_FROM", "onboarding@resend.dev"),
            "to": to_email,
            "subject": subject,
            "html": html,
        })
    except Exception as exc:
        raise error_type("Unable to send email") from exc


def send_email_verification(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    verify_url = f"{frontend_url}/verify-email/{uid}/{token}/"

    _send_resend_email(
        to_email=user.email,
        subject="Verify your AjnihaStay email",
        html=(
            "<h2>Verify your email</h2>"
            "<p>Confirm your email address to activate your AjnihaStay login.</p>"
            f'<a href="{verify_url}">Verify Email</a>'
        ),
        error_type=EmailVerificationDeliveryError,
    )


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"

    _send_resend_email(
        to_email=user.email,
        subject="Reset your password",
        html=(
            "<h2>Password Reset</h2>"
            "<p>Use the link below to reset your password.</p>"
            f'<a href="{reset_url}">Reset Password</a>'
        ),
        error_type=PasswordResetDeliveryError,
    )
