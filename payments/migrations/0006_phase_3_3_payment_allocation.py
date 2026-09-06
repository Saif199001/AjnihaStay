from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def backfill_payment_workspaces(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.select_related(
        "invoice__occupancy__tenant"
    ).iterator():
        payment.workspace_id = payment.invoice.occupancy.tenant.workspace_id
        payment.save(update_fields=["workspace"])


def reverse_payment_workspaces(apps, schema_editor):
    # Workspace ownership is derived from the legacy invoice relationship in
    # the pre-Phase-3.3 schema. There is no safe destructive reverse operation.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0005_delete_integrity"),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="workspaces.workspace",
            ),
        ),
        migrations.RunPython(
            backfill_payment_workspaces,
            reverse_payment_workspaces,
        ),
        migrations.AlterField(
            model_name="payment",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="workspaces.workspace",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="payments.invoice",
            ),
        ),
        migrations.CreateModel(
            name="PaymentAllocation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="payments.invoice",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="payments.payment",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["payment"], name="payments_pa_payment_id_8d2c1e_idx"),
                    models.Index(fields=["invoice"], name="payments_pa_invoice_id_0f2b43_idx"),
                    models.Index(fields=["invoice", "created_at"], name="payments_pa_invoice_3b3d9c_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(amount__gt=0),
                        name="payment_allocation_amount_positive",
                    ),
                ],
            },
        ),
    ]
