from django.db import migrations


REASON_CONSTRAINT = (
    "payments_financialadjustment_reason_non_blank"
)


def add_reason_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE payments_financialadjustment "
            f"ADD CONSTRAINT {REASON_CONSTRAINT} "
            "CHECK (btrim(reason) <> '')"
        )


def remove_reason_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE payments_financialadjustment "
            f"DROP CONSTRAINT IF EXISTS {REASON_CONSTRAINT}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0012_financial_adjustment"),
    ]

    operations = [
        migrations.RunPython(add_reason_constraint, remove_reason_constraint),
    ]
