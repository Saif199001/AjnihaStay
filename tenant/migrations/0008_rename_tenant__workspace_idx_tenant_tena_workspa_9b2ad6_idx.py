from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0007_merge_workspace_and_legacy"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="tenant",
            new_name="tenant_tena_workspa_9b2ad6_idx",
            old_name="tenant__workspace_idx",
        ),
    ]
