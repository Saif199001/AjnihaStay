from django.db import migrations, models
import django.db.models.deletion


def assign_workspaces(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    Workspace = apps.get_model("workspaces", "Workspace")
    for prop in Property.objects.all().iterator():
        workspace = Workspace.objects.filter(owner_id=prop.owner_id, is_active=True).order_by("pk").first()
        if workspace:
            prop.workspace_id = workspace.pk
            prop.save(update_fields=["workspace"])


def clear_workspaces(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    Property.objects.update(workspace=None)


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0001_initial"),
        ("workspaces", "0002_bootstrap_workspaces"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="properties",
                to="workspaces.workspace",
            ),
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["workspace", "is_active"], name="properties__workspace_idx"),
        ),
        migrations.RunPython(assign_workspaces, clear_workspaces),
        migrations.AlterField(
            model_name="property",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="properties",
                to="workspaces.workspace",
            ),
        ),
    ]
