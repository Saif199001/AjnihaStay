from django.db import migrations, models


def preserve_account_state(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_active_account=False).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_remove_staff_role"),
    ]

    operations = [
        migrations.RunPython(
            preserve_account_state,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="user",
            name="is_active_account",
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
