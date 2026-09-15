from django.db import migrations, models
from django.db.models import Q


def backfill_schedule_anchor_and_duplicates(apps, schema_editor):
    BillingSchedule = apps.get_model("payments", "BillingSchedule")
    db_alias = schema_editor.connection.alias

    for schedule in BillingSchedule.objects.using(db_alias).filter(
        frequency="monthly", anchor_day__isnull=True
    ).order_by("id"):
        BillingSchedule.objects.using(db_alias).filter(pk=schedule.pk).update(
            anchor_day=schedule.next_run_date.day
        )

    seen = set()
    for schedule in BillingSchedule.objects.using(db_alias).filter(
        active=True
    ).order_by("occupancy_id", "id"):
        if schedule.occupancy_id in seen:
            BillingSchedule.objects.using(db_alias).filter(pk=schedule.pk).update(active=False)
        else:
            seen.add(schedule.occupancy_id)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0021_invoice_billing_period_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingschedule",
            name="anchor_day",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_schedule_anchor_and_duplicates, noop),
        migrations.AddConstraint(
            model_name="billingschedule",
            constraint=models.CheckConstraint(
                condition=Q(anchor_day__isnull=True) | Q(anchor_day__gte=1, anchor_day__lte=31),
                name="billing_schedule_anchor_day_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="billingschedule",
            constraint=models.UniqueConstraint(
                condition=Q(active=True),
                fields=("occupancy",),
                name="billing_schedule_one_active_per_occupancy",
            ),
        ),
    ]
