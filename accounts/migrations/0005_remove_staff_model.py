from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_email_verification"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Staff",
        ),
    ]
