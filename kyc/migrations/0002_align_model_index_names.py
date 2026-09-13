from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("kyc", "0001_p16_kyc_foundation"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="agreementlink",
            old_name="agreement_ws_tenant_idx",
            new_name="kyc_agreeme_workspa_bef5bc_idx",
        ),
        migrations.RenameIndex(
            model_name="agreementlink",
            old_name="agreement_ws_occ_idx",
            new_name="kyc_agreeme_workspa_f5b5af_idx",
        ),
        migrations.RenameIndex(
            model_name="agreementlink",
            old_name="agreement_ws_lease_idx",
            new_name="kyc_agreeme_workspa_8687fb_idx",
        ),
        migrations.RenameIndex(
            model_name="kycdocument",
            old_name="kyc_doc_ws_tenant_status_idx",
            new_name="kyc_kycdocu_workspa_db2a88_idx",
        ),
        migrations.RenameIndex(
            model_name="kycdocument",
            old_name="kyc_doc_ws_expiry_idx",
            new_name="kyc_kycdocu_workspa_d44fbb_idx",
        ),
        migrations.RenameIndex(
            model_name="kycprofile",
            old_name="kyc_profile_ws_status_idx",
            new_name="kyc_kycprof_workspa_4e04e7_idx",
        ),
        migrations.RenameIndex(
            model_name="kycverificationevent",
            old_name="kyc_event_ws_tenant_time_idx",
            new_name="kyc_kycveri_workspa_1e572a_idx",
        ),
    ]
