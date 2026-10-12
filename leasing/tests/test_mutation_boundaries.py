from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import models
from django.test import SimpleTestCase

from leasing.models import CONTRACTUAL_FIELDS, Lease, LeaseQuerySet
from leasing.lifecycle_models import (
    LeaseContractVersion,
    LeaseContractVersionQuerySet,
    LeaseLifecycleEvent,
    LeaseLifecycleEventQuerySet,
)


class LeaseModelMutationBoundaryTests(SimpleTestCase):
    def _previous_lease_values(self, **overrides):
        values = {
            "status": Lease.STATUS_ACTIVE,
            "workspace_id": 1,
            "occupancy_id": 2,
            "agreement_number": "LEASE-1",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "rent_amount": Decimal("10000.00"),
            "security_deposit": Decimal("5000.00"),
            "notice_period_days": 30,
            "terms": {"maintenance": "owner"},
            "agreement_reference": "contract.pdf",
            "created_by_id": 7,
        }
        values.update(overrides)
        return values

    def _lease(self):
        lease = Lease(
            workspace_id=1,
            occupancy_id=2,
            agreement_number="LEASE-1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent_amount=Decimal("10000.00"),
            security_deposit=Decimal("5000.00"),
            notice_period_days=30,
            terms={"maintenance": "owner"},
            agreement_reference="contract.pdf",
            created_by_id=7,
            status=Lease.STATUS_ACTIVE,
        )
        lease.pk = 99
        return lease

    @patch.object(models.Model, "save")
    @patch.object(Lease, "clean")
    def test_new_lease_cannot_bypass_canonical_creation_with_active_status(self, clean_mock, base_save):
        lease = Lease(
            workspace_id=1,
            occupancy_id=2,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent_amount=Decimal("10000.00"),
            created_by_id=7,
            status=Lease.STATUS_ACTIVE,
        )

        with self.assertRaisesMessage(ValidationError, "must start in draft status"):
            lease.save()

        clean_mock.assert_not_called()
        base_save.assert_not_called()

    @patch.object(models.Model, "save")
    @patch.object(Lease, "clean")
    @patch.object(Lease.objects, "filter")
    def test_active_lease_save_rejects_contractual_fact_changes(self, filter_mock, clean_mock, base_save):
        filter_mock.return_value.values.return_value.first.return_value = self._previous_lease_values()
        lease = self._lease()
        lease.rent_amount = Decimal("12000.00")

        with self.assertRaisesMessage(ValidationError, "immutable after activation"):
            lease.save()

        base_save.assert_not_called()

    @patch.object(models.Model, "save")
    @patch.object(Lease, "clean")
    @patch.object(Lease.objects, "filter")
    def test_active_lease_save_rejects_workspace_and_occupancy_reassignment(self, filter_mock, clean_mock, base_save):
        filter_mock.return_value.values.return_value.first.return_value = self._previous_lease_values()
        lease = self._lease()
        lease.workspace_id = 88

        with self.assertRaisesMessage(ValidationError, "immutable after activation"):
            lease.save()

        base_save.assert_not_called()

    @patch.object(models.QuerySet, "update")
    @patch.object(LeaseQuerySet, "filter")
    def test_queryset_update_rejects_contract_mutation_when_active_rows_match(self, filter_mock, base_update):
        filter_mock.return_value.exists.return_value = True
        queryset = LeaseQuerySet(model=Lease, query=Mock())

        with self.assertRaisesMessage(ValidationError, "immutable after activation"):
            queryset.update(rent_amount=Decimal("1.00"))

        base_update.assert_not_called()

    @patch.object(models.QuerySet, "update")
    @patch.object(LeaseQuerySet, "filter")
    def test_queryset_update_allows_contract_mutation_when_only_draft_rows_match(self, filter_mock, base_update):
        filter_mock.return_value.exists.return_value = False
        queryset = LeaseQuerySet(model=Lease, query=Mock())
        base_update.return_value = 1

        result = queryset.update(rent_amount=Decimal("11000.00"))

        self.assertEqual(result, 1)
        base_update.assert_called_once_with(rent_amount=Decimal("11000.00"))

    @patch.object(models.QuerySet, "bulk_update")
    @patch.object(Lease.objects, "filter")
    def test_bulk_update_rejects_contract_mutation_when_active_rows_match(self, filter_mock, base_bulk_update):
        filter_mock.return_value.exists.return_value = True
        queryset = LeaseQuerySet(model=Lease, query=Mock())
        lease = self._lease()
        lease.rent_amount = Decimal("12000.00")

        with self.assertRaisesMessage(ValidationError, "immutable after activation"):
            queryset.bulk_update([lease], ["rent_amount"])

        base_bulk_update.assert_not_called()

    def test_status_is_not_a_contract_field_and_remains_service_only(self):
        self.assertNotIn("status", CONTRACTUAL_FIELDS)
        queryset = LeaseQuerySet(model=Lease, query=Mock())

        with self.assertRaisesMessage(ValidationError, "canonical lifecycle service"):
            queryset.update(status=Lease.STATUS_EXPIRED)



class ImmutableLeaseHistoryDeletionTests(SimpleTestCase):
    @patch.object(models.QuerySet, "delete")
    def test_lifecycle_event_queryset_delete_is_rejected(self, base_delete):
        queryset = LeaseLifecycleEventQuerySet(
            model=LeaseLifecycleEvent, query=Mock()
        )

        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            queryset.delete()

        base_delete.assert_not_called()

    def test_lifecycle_event_instance_delete_is_rejected(self):
        event = LeaseLifecycleEvent()
        event.pk = 10

        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            event.delete()

    @patch.object(models.QuerySet, "delete")
    def test_contract_version_queryset_delete_is_rejected(self, base_delete):
        queryset = LeaseContractVersionQuerySet(
            model=LeaseContractVersion, query=Mock()
        )

        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            queryset.delete()

        base_delete.assert_not_called()

    def test_contract_version_instance_delete_is_rejected(self):
        version = LeaseContractVersion()
        version.pk = 10

        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            version.delete()
