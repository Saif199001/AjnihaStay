from django.db import migrations
from django.utils.text import slugify


def bootstrap_workspaces(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Workspace = apps.get_model("workspaces", "Workspace")
    Membership = apps.get_model("workspaces", "Membership")

    for user in User.objects.order_by("pk"):
        existing = Workspace.objects.filter(owner_id=user.pk).order_by("pk").first()
        if existing:
            workspace = existing
        else:
            base = slugify((user.email or "workspace").split("@")[0]) or "workspace"
            slug = base
            counter = 2
            while Workspace.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1

            workspace = Workspace.objects.create(
                name=f"{user.email}'s Workspace",
                slug=slug,
                owner_id=user.pk,
            )

        Membership.objects.update_or_create(
            workspace_id=workspace.pk,
            user_id=user.pk,
            defaults={"role": "owner", "is_active": True},
        )


def reverse_bootstrap(apps, schema_editor):
    Membership = apps.get_model("workspaces", "Membership")
    Workspace = apps.get_model("workspaces", "Workspace")
    Membership.objects.all().delete()
    Workspace.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(bootstrap_workspaces, reverse_bootstrap),
    ]
