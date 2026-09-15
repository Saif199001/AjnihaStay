from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0019_financial_ledger_append_only")]

    operations = [
        migrations.AlterField(
            model_name="financialledgerentry",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("invoice_created", "Invoice created"),
                    ("payment_recorded", "Payment recorded"),
                    ("payment_allocated", "Payment allocated"),
                    ("advance_credit_created", "Advance credit created"),
                    ("advance_credit_applied", "Advance credit applied"),
                    ("adjustment_created", "Adjustment created"),
                    ("charge_generated", "Charge generated"),
                    ("recurring_invoice_generated", "Recurring invoice generated"),
                    ("late_fee_generated", "Late fee generated"),
                    ("final_settlement_finalized", "Final settlement finalized"),
                    ("refund_requested", "Refund requested"),
                    ("refund_processing", "Refund processing"),
                    ("refund_succeeded", "Refund succeeded"),
                    ("refund_failed", "Refund failed"),
                ],
                max_length=40,
            ),
        ),
    ]
