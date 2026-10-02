from django.db import migrations, models
from django.db.models import Q


def validate_existing_property_structure(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    invalid = Property.objects.exclude(
        Q(property_type__in=["pg", "hostel"], has_subunits=True)
        | Q(
            property_type__in=["shop", "flat", "office", "building"],
            has_subunits=False,
        )
    ).values_list("id", "property_type", "has_subunits")[:20]

    if invalid:
        raise RuntimeError(
            "Cannot apply property structure invariant; existing Property rows "
            f"are inconsistent: {list(invalid)}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0006_property_owner_delete_integrity"),
    ]

    operations = [
        migrations.RunPython(
            validate_existing_property_structure,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="property",
            constraint=models.CheckConstraint(
                condition=(
                    Q(property_type__in=["pg", "hostel"], has_subunits=True)
                    | Q(
                        property_type__in=["shop", "flat", "office", "building"],
                        has_subunits=False,
                    )
                ),
                name="property_type_has_subunits_consistent",
            ),
        ),
    ]
