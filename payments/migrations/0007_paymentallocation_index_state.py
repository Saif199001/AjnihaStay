from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0006_phase_3_3_payment_allocation"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="paymentallocation",
            new_name="payments_pa_payment_bc6702_idx",
            old_name="payments_pa_payment_id_8d2c1e_idx",
        ),
        migrations.RenameIndex(
            model_name="paymentallocation",
            new_name="payments_pa_invoice_16fb19_idx",
            old_name="payments_pa_invoice_id_0f2b43_idx",
        ),
        migrations.RenameIndex(
            model_name="paymentallocation",
            new_name="payments_pa_invoice_6c291f_idx",
            old_name="payments_pa_invoice_3b3d9c_idx",
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["workspace", "invoice"],
                name="payments_pa_workspa_c6e8ac_idx",
            ),
        ),
    ]
