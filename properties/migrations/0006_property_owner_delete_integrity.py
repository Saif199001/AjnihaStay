from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0005_allow_null_images"),
    ]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="properties",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
