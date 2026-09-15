from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0003_document_lifecycle_history"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="kycdocumentevent",
            new_name="kyc_kycdocu_workspa_3789fd_idx",
            old_name="kyc_kycdocume_workspa_2b4a6d_idx",
        ),
    ]
