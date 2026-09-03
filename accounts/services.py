from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from .models import User
from workspaces.models import Membership, Workspace


def _unique_workspace_slug(email):
    base = slugify(email.split("@")[0]) or "workspace"
    slug = base
    counter = 2
    while Workspace.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def create_user_account(email, password, confirm_password, workspace_name=None):
    email = email.lower()

    if password != confirm_password:
        raise ValidationError("Passwords do not match")

    validate_password(password)

    if User.objects.filter(email=email).exists():
        raise ValidationError("Email already exists")

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=password,
            role="owner",
        )
        name = (workspace_name or "").strip() or f"{email}'s Workspace"
        workspace = Workspace.objects.create(
            name=name,
            slug=_unique_workspace_slug(email),
            owner=user,
        )
        Membership.objects.create(
            workspace=workspace,
            user=user,
            role=Membership.ROLE_OWNER,
            is_active=True,
        )

    return user


def login_user_service(request, email, password):
    return authenticate(request, email=email, password=password)
