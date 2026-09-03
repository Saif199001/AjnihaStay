from django.db import migrations, models
import django.db.models.deletion


def assign_workspaces(apps, schema_editor):
    Tenant = apps.get_model("tenant", "Tenant")
    Workspace = apps.get_model("workspaces", "Workspace")
    for tenant in Tenant.objects.all().iterator():
        workspace = Workspace.objects.filter(owner_id=tenant.owner_id, is_active=True).order_by("pk").first()
        if workspace:
            tenant.workspace_id = workspace.pk
            tenant.save(update_fields=["workspace"])


def clear_workspaces(apps, schema_editor):
    Tenant = apps.get_model("tenant", "Tenant")
    Tenant.objects.update(workspace=None)


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0001_initial"),
        ("workspaces", "0002_bootstrap_workspaces"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="workspace_tenants",
                to="workspaces.workspace",
            ),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(fields=["workspace", "created_at"], name="tenant__workspace_idx"),
        ),
        migrations.RunPython(assign_workspaces, clear_workspaces),
        migrations.AlterField(
            model_name="tenant",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="workspace_tenants",
                to="workspaces.workspace",
            ),
        ),
    ]
