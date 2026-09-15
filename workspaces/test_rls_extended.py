from django.db import connection
from django.test import TestCase


NEW_WORKSPACE_TABLES = (
    "applications_applicant",
    "applications_application",
    "applications_applicationevent",
    "kyc_kycprofile",
    "kyc_kycdocument",
    "kyc_kycverificationevent",
    "kyc_kycdocumentevent",
    "kyc_agreementlink",
    "leasing_lease",
    "leasing_leaselifecycleevent",
    "leasing_leasenotice",
    "leasing_leaserenewal",
    "leasing_leasecontractversion",
    "payments_financialadjustment",
    "payments_finalsettlement",
    "payments_financialledgerentry",
)


class WorkspaceRlsExtendedTests(TestCase):
    def test_new_workspace_tables_have_fail_closed_policies(self):
        if connection.vendor != "postgresql":
            self.skipTest("Workspace RLS is PostgreSQL-specific")

        with connection.cursor() as cursor:
            for table in NEW_WORKSPACE_TABLES:
                cursor.execute(
                    """
                    SELECT policyname, qual, with_check
                    FROM pg_policies
                    WHERE schemaname = current_schema() AND tablename = %s
                    """,
                    [table],
                )
                policies = cursor.fetchall()

                self.assertTrue(policies, f"No RLS policy installed for {table}")
                self.assertTrue(
                    any(
                        all(
                            marker in str(expression).lower()
                            for marker in (
                                "nullif(",
                                "current_setting(",
                                "app.workspace_id",
                            )
                        )
                        for expression in (qual, with_check)
                    )
                    and "nullif(" in str(with_check).lower()
                    and "current_setting(" in str(with_check).lower()
                    and "app.workspace_id" in str(with_check).lower()
                    for _, qual, with_check in policies
                ),
                    f"{table} does not have a fail-closed workspace policy",
                )
