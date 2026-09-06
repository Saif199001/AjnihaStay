from django.db import migrations


def backfill_payment_allocations(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    PaymentAllocation = apps.get_model("payments", "PaymentAllocation")

    for payment in Payment.objects.exclude(invoice_id=None).iterator():
        PaymentAllocation.objects.get_or_create(
            payment_id=payment.id,
            invoice_id=payment.invoice_id,
            defaults={"amount": payment.amount},
        )


def reverse_payment_allocations(apps, schema_editor):
    # Historical allocations are financial records and must not be
    # destructively reconstructed or removed on reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0006_phase_3_3_payment_allocation"),
    ]

    operations = [
        migrations.RunPython(
            backfill_payment_allocations,
            reverse_payment_allocations,
        ),
    ]
