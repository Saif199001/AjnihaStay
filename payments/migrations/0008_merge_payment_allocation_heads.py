from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0007_backfill_payment_allocations"),
        ("payments", "0007_paymentallocation_index_state"),
    ]

    operations = []
