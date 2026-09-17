from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_remove_user_role"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="staff",
            name="role",
        ),
    ]
