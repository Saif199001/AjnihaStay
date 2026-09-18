from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_email_verification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
    ]
