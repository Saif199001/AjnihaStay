from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0010_domain_integrity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="tenants",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="occupancy",
            name="tenant",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="occupancies",
                to="tenant.tenant",
            ),
        ),
        migrations.AlterField(
            model_name="occupancy",
            name="unit",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="occupancies",
                to="unit.unit",
            ),
        ),
        migrations.AlterField(
            model_name="occupancy",
            name="subunit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="occupancies",
                to="unit.subunit",
            ),
        ),
        migrations.AlterField(
            model_name="charge",
            name="occupancy",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="charges",
                to="tenant.occupancy",
            ),
        ),
    ]
