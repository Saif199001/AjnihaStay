from django.db import migrations
import cloudinary.models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0004_rename_properties__workspace_idx_properties__workspa_6c7f91_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="thumbnail",
            field=cloudinary.models.CloudinaryField(
                blank=True,
                default=None,
                max_length=255,
                null=True,
                verbose_name="properties",
            ),
        ),
        migrations.AlterField(
            model_name="propertyimage",
            name="image",
            field=cloudinary.models.CloudinaryField(
                blank=True,
                default=None,
                max_length=255,
                null=True,
                verbose_name="properties",
            ),
        ),
    ]
