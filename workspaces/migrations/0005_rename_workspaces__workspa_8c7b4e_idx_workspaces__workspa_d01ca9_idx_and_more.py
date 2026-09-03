from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0004_strengthen_workspace_rls"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="membership",
            new_name="workspaces__workspa_d01ca9_idx",
            old_name="workspaces__workspa_8c7b4e_idx",
        ),
        migrations.RenameIndex(
            model_name="membership",
            new_name="workspaces__user_id_64f055_idx",
            old_name="workspaces__user_id_7d11df_idx",
        ),
        migrations.RenameIndex(
            model_name="workspace",
            new_name="workspaces__owner_i_be377b_idx",
            old_name="workspaces__owner_i_9f4a65_idx",
        ),
    ]
