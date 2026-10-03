from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils.datastructures import MultiValueDict

from accounts.services import create_user_account
from properties.services import create_property
from tenant.services import create_occupancy, create_tenant
from unit.models import SubUnit, _allow_unit_mutation
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class OccupancyOverlapConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = create_user_account(
            "t9-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "T9 Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "T9 Property",
                "property_type": "pg",
                "description": "",
                "address": "Test Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226001",
                "amenities": [],
            },
            MultiValueDict(),
        )
        self.unit = create_unit(
            self.owner,
            self.workspace,
            {
                "property": self.property,
                "unit_number": "T9-101",
                "unit_type": "room",
                "rent": Decimal("10000"),
                "capacity": 1,
                "description": "",
            },
        )

        self.tenants = [
            create_tenant(
                self.owner,
                self.workspace,
                {
                    "full_name": f"T9 Tenant {index}",
                    "phone": f"98765432{10 + index}",
                    "permanent_address": "Test Address",
                },
                MultiValueDict(),
            )
            for index in range(2)
        ]

    def _occupancy_data(
        self,
        tenant,
        *,
        check_in=date(2026, 11, 1),
        check_out=date(2026, 11, 10),
    ):
        return {
            "tenant": tenant.pk,
            "unit": self.unit.pk,
            "rent": Decimal("10000"),
            "billing_type": "advance",
            "billing_cycle": "monthly",
            "check_in_date": check_in,
            "check_out_date": check_out,
            "next_due_date": date(2026, 12, 1),
            "security_deposit": Decimal("10000"),
            "deposit_paid": False,
        }

    def _create_concurrent_occupancy(self, tenant_id):
        close_old_connections()
        try:
            from tenant.models import Tenant

            tenant = Tenant.objects.get(pk=tenant_id)
            return create_occupancy(
                self.owner,
                self.workspace,
                self._occupancy_data(tenant),
            )
        except Exception as exc:
            return exc
        finally:
            close_old_connections()

    def test_capacity_one_allows_exactly_one_concurrent_occupancy(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    self._create_concurrent_occupancy,
                    [tenant.pk for tenant in self.tenants],
                )
            )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValidationError)
        self.assertEqual(
            self.unit.occupancies.filter(is_active=True).count(),
            1,
        )

    def test_same_subunit_allows_exactly_one_concurrent_occupancy(self):
        with _allow_unit_mutation():
            subunit = SubUnit.objects.create(
                unit=self.unit,
                subunit_number="T9-BED-1",
                rent=Decimal("10000"),
            )

        def attempt(tenant_id):
            close_old_connections()
            try:
                from tenant.models import Tenant

                tenant = Tenant.objects.get(pk=tenant_id)
                data = self._occupancy_data(tenant)
                data["subunit"] = subunit.pk
                data.pop("unit")
                return create_occupancy(self.owner, self.workspace, data)
            except Exception as exc:
                return exc
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    attempt,
                    [tenant.pk for tenant in self.tenants],
                )
            )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValidationError)
        self.assertEqual(
            subunit.occupancies.filter(is_active=True).count(),
            1,
        )

    def test_non_overlapping_dates_are_allowed(self):
        create_occupancy(
            self.owner,
            self.workspace,
            self._occupancy_data(
                self.tenants[0],
                check_in=date(2026, 11, 1),
                check_out=date(2026, 11, 10),
            ),
        )
        create_occupancy(
            self.owner,
            self.workspace,
            self._occupancy_data(
                self.tenants[1],
                check_in=date(2026, 11, 11),
                check_out=date(2026, 11, 20),
            ),
        )

        self.assertEqual(
            self.unit.occupancies.filter(is_active=True).count(),
            2,
        )

    def test_checkout_and_next_checkin_same_date_are_treated_as_overlap(self):
        create_occupancy(
            self.owner,
            self.workspace,
            self._occupancy_data(
                self.tenants[0],
                check_in=date(2026, 11, 1),
                check_out=date(2026, 11, 10),
            ),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Unit capacity is full for selected dates",
        ):
            create_occupancy(
                self.owner,
                self.workspace,
                self._occupancy_data(
                    self.tenants[1],
                    check_in=date(2026, 11, 10),
                    check_out=date(2026, 11, 20),
                ),
            )
