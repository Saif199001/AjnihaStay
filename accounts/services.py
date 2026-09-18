from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.text import slugify

from .models import User
from workspaces.models import Membership, Workspace


def _workspace_slug_candidates(email):
    base = slugify(email.split("@")[0]) or "workspace"
    yield base
    counter = 2
    while True:
        yield f"{base}-{counter}"
        counter += 1


def _unique_workspace_slug(email):
    return next(
        slug
        for slug in _workspace_slug_candidates(email)
        if not Workspace.objects.filter(slug=slug).exists()
    )


def _create_workspace_with_unique_slug(name, email, owner):
    slug = _unique_workspace_slug(email)
    counter = 2
    base = slug

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
