from django.db import migrations, models
from django.db.models import Q


def validate_existing_rents(apps, schema_editor):
    Unit = apps.get_model("unit", "Unit")
    SubUnit = apps.get_model("unit", "SubUnit")

    invalid_units = list(
        Unit.objects.filter(
            Q(rent__isnull=True) | Q(rent__lte=0)
        ).values_list("id", "rent")[:20]
    )
    if invalid_units:
        raise RuntimeError(
            "P6 rent migration blocked: Unit records must have rent > 0. "
            f"Invalid examples: {invalid_units}"
        )

    invalid_subunits = list(
        SubUnit.objects.filter(
            Q(rent__isnull=True) | Q(rent__lte=0)
        ).values_list("id", "rent")[:20]
    )
    if invalid_subunits:
        raise RuntimeError(
            "P6 rent migration blocked: SubUnit records must have rent > 0. "
            f"Invalid examples: {invalid_subunits}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("unit", "0005_capacity_rent_integrity"),
    ]

    operations = [
        migrations.RunPython(
            validate_existing_rents,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="unit",
            name="rent",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                blank=False,
                null=False,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="unit",
            name="unit_rent_non_negative",
        ),
        migrations.RemoveConstraint(
            model_name="subunit",
            name="subunit_rent_non_negative",
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.CheckConstraint(
                condition=Q(rent__gt=0),
                name="unit_rent_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="subunit",
            constraint=models.CheckConstraint(
                condition=Q(rent__gt=0),
                name="subunit_rent_positive",
            ),
        ),
    ]
