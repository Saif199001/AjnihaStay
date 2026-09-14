from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="applicant",
            old_name="applications_applicant_workspace_created_idx",
            new_name="applicant_ws_created_idx",
        ),
        migrations.RenameIndex(
            model_name="applicant",
            old_name="applications_applicant_workspace_phone_idx",
            new_name="applicant_ws_phone_idx",
        ),
        migrations.RenameIndex(
            model_name="application",
            old_name="applications_application_workspace_status_created_idx",
            new_name="app_ws_status_created_idx",
        ),
        migrations.RenameIndex(
            model_name="application",
            old_name="applications_application_workspace_applicant_property_status_idx",
            new_name="app_ws_applicant_property_idx",
        ),
        migrations.RenameIndex(
            model_name="applicationevent",
            old_name="applications_event_workspace_application_occurred_idx",
            new_name="event_ws_app_occurred_idx",
        ),
    ]
