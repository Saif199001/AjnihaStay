from django.db import migrations, models
from django.db.models import Count


def validate_invoice_period_identity(apps, schema_editor):
    Invoice = apps.get_model("payments", "Invoice")
    duplicates = list(
        Invoice.objects.values("occupancy_id", "billing_start", "billing_end")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("occupancy_id", "billing_start", "billing_end")[:20]
    )
    if duplicates:
        examples = ", ".join(
            f"occupancy={row['occupancy_id']} start={row['billing_start']} end={row['billing_end']} count={row['row_count']}"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce invoice billing-period uniqueness because duplicate "
            f"financial records exist. Resolve these records before deployment: {examples}"
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0020_remove_invoice_lifecycle_ledger_event"),
    ]

    operations = [
        migrations.RunPython(validate_invoice_period_identity, noop),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.UniqueConstraint(
                fields=["occupancy", "billing_start", "billing_end"],
                name="invoice_occupancy_billing_period_uniq",
            ),
        ),
    ]
