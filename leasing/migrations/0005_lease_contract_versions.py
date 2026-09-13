from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Q


def backfill_initial_contract_versions(apps, schema_editor):
    Lease = apps.get_model("leasing", "Lease")
    LeaseRenewal = apps.get_model("leasing", "LeaseRenewal")
    LeaseContractVersion = apps.get_model("leasing", "LeaseContractVersion")
    db_alias = schema_editor.connection.alias

    for lease in Lease.objects.using(db_alias).all().iterator():
        LeaseContractVersion.objects.using(db_alias).create(
            lease_id=lease.id,
            workspace_id=lease.workspace_id,
            version_number=1,
            predecessor_id=None,
            start_date=lease.start_date,
            end_date=lease.end_date,
            rent_amount=lease.rent_amount,
            security_deposit=lease.security_deposit,
            notice_period_days=lease.notice_period_days,
            terms=lease.terms,
            agreement_reference=lease.agreement_reference,
            created_by_id=lease.created_by_id,
        )

        predecessor = LeaseContractVersion.objects.using(db_alias).get(lease_id=lease.id, version_number=1)
        confirmed_renewals = (
            LeaseRenewal.objects.using(db_alias)
            .filter(source_lease_id=lease.id, status="confirmed")
            .order_by("renewal_number", "id")
        )
        for renewal in confirmed_renewals:
            version = LeaseContractVersion.objects.using(db_alias).create(
                lease_id=lease.id,
                workspace_id=lease.workspace_id,
                version_number=predecessor.version_number + 1,
                predecessor_id=predecessor.id,
                start_date=renewal.start_date,
                end_date=renewal.end_date,
                rent_amount=renewal.rent_amount,
                security_deposit=renewal.security_deposit,
                notice_period_days=renewal.notice_period_days,
                terms=renewal.terms,
                agreement_reference=renewal.agreement_reference,
                created_by_id=renewal.created_by_id,
            )
            renewal.successor_version_id = version.id
            renewal.save(update_fields=["successor_version"])
            predecessor = version


def remove_contract_versions(apps, schema_editor):
    LeaseRenewal = apps.get_model("leasing", "LeaseRenewal")
    LeaseContractVersion = apps.get_model("leasing", "LeaseContractVersion")
    db_alias = schema_editor.connection.alias
    LeaseRenewal.objects.using(db_alias).update(successor_version_id=None)
    LeaseContractVersion.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("leasing", "0004_lease_renewal"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaseContractVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("rent_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("security_deposit", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("notice_period_days", models.PositiveIntegerField(default=0)),
                ("terms", models.JSONField(blank=True, default=dict)),
                ("agreement_reference", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_contract_versions_created", to="accounts.user")),
                ("lease", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_versions", to="leasing.lease")),
                ("predecessor", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="successor", to="leasing.leasecontractversion")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_contract_versions", to="workspaces.workspace")),
            ],
            options={
                "ordering": ["lease_id", "version_number"],
                "indexes": [
                    models.Index(fields=["workspace", "lease", "version_number"], name="lease_ver_ws_lease_num_idx"),
                    models.Index(fields=["workspace", "start_date"], name="lease_ver_ws_start_idx"),
                    models.Index(fields=["workspace", "end_date"], name="lease_ver_ws_end_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=["lease", "version_number"], name="lease_ver_lease_num_uniq"),
                    models.CheckConstraint(condition=Q(version_number__gte=1), name="lease_ver_num_positive"),
                    models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="lease_ver_end_gte_start"),
                    models.CheckConstraint(condition=Q(rent_amount__gte=0), name="lease_ver_rent_non_negative"),
                    models.CheckConstraint(condition=Q(security_deposit__gte=0), name="lease_ver_dep_non_negative"),
                ],
            },
        ),
        migrations.AddField(
            model_name="leaserenewal",
            name="successor_version",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="source_renewal", to="leasing.leasecontractversion"),
        ),
        migrations.RunPython(backfill_initial_contract_versions, remove_contract_versions),
        migrations.RunSQL(
            sql="""
                ALTER TABLE leasing_leasecontractversion ENABLE ROW LEVEL SECURITY;
                ALTER TABLE leasing_leasecontractversion FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS workspace_isolation_leasingleasecontractversion ON leasing_leasecontractversion;
                CREATE POLICY workspace_isolation_leasingleasecontractversion
                    ON leasing_leasecontractversion
                    USING (workspace_id = current_setting('app.current_workspace_id', true)::bigint)
                    WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::bigint);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS workspace_isolation_leasingleasecontractversion ON leasing_leasecontractversion;
                ALTER TABLE leasing_leasecontractversion NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE leasing_leasecontractversion DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
