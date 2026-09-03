from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0003_property_has_subunits_alter_property_property_type"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="property",
            new_name="properties__workspa_6c7f91_idx",
            old_name="properties__workspace_idx",
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["property_type"], name="properties__propert_5c7790_idx"),
        ),
    ]
