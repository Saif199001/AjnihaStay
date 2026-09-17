from django.db import migrations, models


def migrate_staff_to_viewer(apps, schema_editor):
    Membership = apps.get_model("workspaces", "Membership")
    Membership.objects.filter(role="staff").update(role="viewer")


def reverse_noop(apps, schema_editor):
    # Do not convert legitimate viewer memberships back into the retired staff role.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0006_rls_fail_closed"),
    ]

    operations = [
        migrations.RunPython(migrate_staff_to_viewer, reverse_noop),
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("admin", "Admin"),
                    ("manager", "Manager"),
                    ("viewer", "Viewer"),
                ],
                default="viewer",
                max_length=20,
            ),
        ),
    ]
