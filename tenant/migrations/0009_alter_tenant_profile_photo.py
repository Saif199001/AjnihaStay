from django.db import migrations
import cloudinary.models


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0008_rename_tenant__workspace_idx_tenant_tena_workspa_9b2ad6_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="profile_photo",
            field=cloudinary.models.CloudinaryField(
                "tenants_photo",
                blank=True,
                null=True,
                default=None,
            ),
        ),
    ]
