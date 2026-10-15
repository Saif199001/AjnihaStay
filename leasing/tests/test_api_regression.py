from datetime import date, timedelta
from unittest.mock import patch
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase
from django.utils import timezone
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIClient

from accounts.services import create_user_account
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent, LeaseRenewal
from leasing.lease_service import create_lease, update_lease
from leasing.models import Lease
from leasing.renewal_service import create_renewal as create_renewal_service
from properties.services import create_property
from tenant.services import create_occupancy, create_tenant
from unit.services import create_unit
from workspaces.models import Membership
from workspaces.services import add_member


class LeaseCreationAPIRegressionTests(TestCase):
    """HTTP-level regression coverage for canonical Lease creation boundaries."""

    def setUp(self):
        self.client = APIClient()
        self.owner = create_user_account(
            "lease-api-owner@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Workspace",
        )
        self.workspace = self.owner.owned_workspaces.get()
        owner_membership = self.owner.workspace_memberships.get()

        self.manager = create_user_account(
            "lease-api-manager@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Manager Workspace",
        )
        self.viewer = create_user_account(
            "lease-api-viewer@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Viewer Workspace",
        )
        add_member(
            self.workspace,
            owner_membership,
            self.manager.email,
            Membership.ROLE_MANAGER,
        )
        add_member(
            self.workspace,
            owner_membership,
            self.viewer.email,
            Membership.ROLE_VIEWER,
        )

        self.property = create_property(
            self.owner,
            self.workspace,
            {
                "owner": self.owner,
                "name": "Lease API Property",
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
                "unit_number": "LEASE-101",
                "unit_type": "room",
                "rent": Decimal("10000.00"),
                "capacity": 1,
                "description": "",
            },
        )
        self.occupancy = self.create_occupancy_record()

    def authenticate(self, user, workspace=None):
        self.client.force_authenticate(user=user)
        active_workspace = workspace or self.workspace
        return {"HTTP_X_WORKSPACE_ID": str(active_workspace.pk)}

    def create_occupancy_record(self, owner=None, workspace=None, unit=None):
        owner = owner or self.owner
        workspace = workspace or self.workspace
        unit = unit or self.unit
        tenant = create_tenant(
            owner,
            workspace,
            {
                "full_name": "Lease API Tenant",
                "phone": "9876543210",
                "permanent_address": "Test Address",
            },
            MultiValueDict(),
        )
        return create_occupancy(
            owner,
            workspace,
            {
                "tenant": tenant.pk,
                "unit": unit.pk,
                "rent": Decimal("10000.00"),
                "billing_type": "advance",
                "billing_cycle": "monthly",
                "check_in_date": date(2026, 10, 1),
                "check_out_date": None,
                "next_due_date": date(2026, 11, 1),
                "security_deposit": Decimal("10000.00"),
                "deposit_paid": False,
            },
        )

    def lease_payload(self, occupancy=None, **overrides):
        payload = {
            "occupancy": (occupancy or self.occupancy).pk,
            "agreement_number": "LEASE-API-001",
            "start_date": "2026-10-01",
            "end_date": "2027-09-30",
            "rent_amount": "10000.00",
            "security_deposit": "10000.00",
            "notice_period_days": 30,
            "terms": {"maintenance": "owner"},
            "agreement_reference": "contract-reference",
        }
        payload.update(overrides)
        return payload

    def create_lease_through_api(self, user=None, **payload_overrides):
        headers = self.authenticate(user or self.manager)
        return self.client.post(
            "/api/leases/create/",
            self.lease_payload(**payload_overrides),
            format="json",
            **headers,
        )

    def test_create_requires_authentication(self):
        response = self.client.post(
            "/api/leases/create/",
            self.lease_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_viewer_cannot_create_lease(self):
        response = self.create_lease_through_api(user=self.viewer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Lease.objects.filter(occupancy=self.occupancy).exists())

    def test_manager_creates_draft_lease_through_canonical_api(self):
        response = self.create_lease_through_api()

        self.assertEqual(response.status_code, 201, response.data)
        lease = Lease.objects.get(occupancy=self.occupancy)
        self.assertEqual(response.data["data"]["id"], lease.pk)
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)
        self.assertEqual(lease.workspace_id, self.workspace.pk)
        self.assertEqual(lease.created_by_id, self.manager.pk)
        self.assertTrue(
            LeaseLifecycleEvent.objects.filter(
                lease=lease,
                event_type=LeaseLifecycleEvent.EVENT_CREATED,
            ).exists()
        )

    def test_duplicate_occupancy_returns_controlled_http_400(self):
        first = self.create_lease_through_api()
        self.assertEqual(first.status_code, 201, first.data)

        second = self.create_lease_through_api(
            agreement_number="LEASE-API-DUPLICATE"
        )
        self.assertEqual(second.status_code, 400, second.data)
        # ModelSerializer's OneToOne uniqueness validator returns field errors
        # before the canonical service is called.
        self.assertIn("occupancy", second.data, second.data)
        self.assertEqual(Lease.objects.filter(occupancy=self.occupancy).count(), 1)

    def test_lease_rent_must_be_strictly_positive_at_api_boundary(self):
        for rent in ("0.00", "-1.00"):
            response = self.create_lease_through_api(
                rent_amount=rent,
                agreement_number=f"LEASE-API-INVALID-RENT-{rent}",
            )
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Lease.objects.filter(occupancy=self.occupancy).exists())

    def test_lease_and_renewal_services_reject_non_positive_rent(self):
        created_for_update = self.create_lease_through_api()
        self.assertEqual(created_for_update.status_code, 201, created_for_update.data)
        update_lease_id = created_for_update.data["data"]["id"]

        for rent in (Decimal("0.00"), Decimal("-1.00")):
            with self.subTest(service="lease_create", rent=rent):
                with self.assertRaisesMessage(ValidationError, "greater than zero"):
                    create_lease(
                        user=self.manager,
                        workspace=self.workspace,
                        data=self.lease_payload(rent_amount=str(rent)),
                    )
            with self.subTest(service="lease_update", rent=rent):
                with self.assertRaisesMessage(ValidationError, "greater than zero"):
                    update_lease(
                        user=self.manager,
                        workspace=self.workspace,
                        lease_id=update_lease_id,
                        changes={"rent_amount": rent},
                    )

        lease_id, _headers = self.create_active_lease()
        for rent in (Decimal("0.00"), Decimal("-1.00")):
            with self.subTest(service="renewal_create", rent=rent):
                with self.assertRaisesMessage(ValidationError, "greater than zero"):
                    create_renewal_service(
                        user=self.manager,
                        workspace=self.workspace,
                        source_lease_id=lease_id,
                        data={
                            "start_date": date(2027, 10, 1),
                            "end_date": date(2028, 9, 30),
                            "rent_amount": rent,
                        },
                    )
        self.assertFalse(LeaseRenewal.objects.filter(source_lease_id=lease_id).exists())

    def test_renewal_serializer_rejects_non_positive_rent(self):
        lease_id, headers = self.create_active_lease()
        url = f"/api/leases/{lease_id}/renewals/create/"
        for rent in ("0.00", "-1.00"):
            response = self.client.post(
                url,
                {
                    "start_date": "2027-10-01",
                    "end_date": "2028-09-30",
                    "rent_amount": rent,
                },
                format="json",
                **headers,
            )
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(LeaseRenewal.objects.filter(source_lease_id=lease_id).exists())

    def test_rent_model_validation_requires_positive_values(self):
        lease_id, _headers = self.create_active_lease()
        lease = Lease.objects.get(pk=lease_id)
        lease.rent_amount = Decimal("0.00")
        with self.assertRaisesMessage(ValidationError, "greater than zero"):
            lease.clean()

        renewal_response = self.create_renewal(lease_id, self.authenticate(self.manager))
        self.assertEqual(renewal_response.status_code, 201, renewal_response.data)
        renewal = LeaseRenewal.objects.get(pk=renewal_response.data["data"]["id"])
        renewal.rent_amount = Decimal("0.00")
        with self.assertRaisesMessage(ValidationError, "greater than zero"):
            renewal.clean()

        version = LeaseContractVersion.objects.get(lease_id=lease_id, version_number=1)
        version.rent_amount = Decimal("0.00")
        with self.assertRaisesMessage(ValidationError, "greater than zero"):
            version.clean()

    def test_database_constraints_reject_non_positive_rent_for_all_contract_records(self):
        lease_id, headers = self.create_active_lease()
        renewal_response = self.create_renewal(lease_id, headers)
        self.assertEqual(renewal_response.status_code, 201, renewal_response.data)
        records = [
            ("lease", Lease.objects.get(pk=lease_id)),
            ("renewal", LeaseRenewal.objects.get(pk=renewal_response.data["data"]["id"])),
            ("contract_version", LeaseContractVersion.objects.get(lease_id=lease_id, version_number=1)),
        ]
        for label, record in records:
            with self.subTest(record=label):
                record.rent_amount = Decimal("0.00")
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT set_config('app.current_workspace_id', %s, true)",
                                [str(self.workspace.pk)],
                            )
                        models.Model.save(record, update_fields=["rent_amount"])

    def test_invalid_lease_payload_returns_http_400(self):
        response = self.create_lease_through_api(
            start_date="2027-01-01",
            end_date="2026-12-31",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Lease.objects.filter(occupancy=self.occupancy).count(), 0)

    def test_occupancy_from_another_workspace_is_rejected(self):
        outsider = create_user_account(
            "lease-api-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Other Workspace",
        )
        other_workspace = outsider.owned_workspaces.get()
        other_property = create_property(
            outsider,
            other_workspace,
            {
                "owner": outsider,
                "name": "Other Lease API Property",
                "property_type": "pg",
                "description": "",
                "address": "Other Address",
                "city": "Lucknow",
                "state": "Uttar Pradesh",
                "pincode": "226002",
                "amenities": [],
            },
            MultiValueDict(),
        )
        other_unit = create_unit(
            outsider,
            other_workspace,
            {
                "property": other_property,
                "unit_number": "OTHER-101",
                "unit_type": "room",
                "rent": Decimal("9000.00"),
                "capacity": 1,
                "description": "",
            },
        )
        other_occupancy = self.create_occupancy_record(
            owner=outsider,
            workspace=other_workspace,
            unit=other_unit,
        )

        response = self.create_lease_through_api(occupancy=other_occupancy)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["error"], "Occupancy not found")
        self.assertFalse(Lease.objects.filter(occupancy=other_occupancy).exists())

    def test_update_and_valid_lifecycle_transitions_use_api_contract(self):
        created = self.create_lease_through_api()
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)

        updated = self.client.post(
            f"/api/leases/{lease_id}/update/",
            {"agreement_number": "LEASE-API-UPDATED"},
            format="json",
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["data"]["agreement_number"], "LEASE-API-UPDATED")

        pending = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_PENDING_SIGNATURE},
            format="json",
            **headers,
        )
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(pending.data["data"]["status"], Lease.STATUS_PENDING_SIGNATURE)

        active = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_ACTIVE},
            format="json",
            **headers,
        )
        self.assertEqual(active.status_code, 200, active.data)
        self.assertEqual(active.data["data"]["status"], Lease.STATUS_ACTIVE)

        invalid_retry = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_DRAFT},
            format="json",
            **headers,
        )
        self.assertEqual(invalid_retry.status_code, 400, invalid_retry.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)
        self.assertIsNotNone(lease.activated_at)

    def test_draft_notice_update_uses_canonical_api(self):
        created = self.create_lease_through_api()
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)
        active = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_PENDING_SIGNATURE},
            format="json",
            **headers,
        )
        self.assertEqual(active.status_code, 200, active.data)
        active = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_ACTIVE},
            format="json",
            **headers,
        )
        self.assertEqual(active.status_code, 200, active.data)
        today = date.today().isoformat()
        notice = self.client.post(
            f"/api/leases/{lease_id}/notices/create/",
            {
                "notice_date": today,
                "effective_date": today,
                "notice_type": "other",
                "reason": "Initial reason",
            },
            format="json",
            **headers,
        )
        self.assertEqual(notice.status_code, 201, notice.data)
        notice_id = notice.data["data"]["id"]
        updated = self.client.post(
            f"/api/leases/notices/{notice_id}/update/",
            {"reason": "Corrected draft reason"},
            format="json",
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["data"]["reason"], "Corrected draft reason")

    def create_active_lease(self, end_date=None):
        created = self.create_lease_through_api(**({"end_date": end_date} if end_date else {}))
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)
        pending = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_PENDING_SIGNATURE},
            format="json",
            **headers,
        )
        self.assertEqual(pending.status_code, 200, pending.data)
        active = self.client.post(
            f"/api/leases/{lease_id}/transition/",
            {"status": Lease.STATUS_ACTIVE},
            format="json",
            **headers,
        )
        self.assertEqual(active.status_code, 200, active.data)
        return lease_id, headers

    def create_renewal(self, lease_id, headers):
        return self.client.post(
            f"/api/leases/{lease_id}/renewals/create/",
            {
                "start_date": "2027-10-01",
                "end_date": "2028-09-30",
                "rent_amount": "10500.00",
                "security_deposit": "10000.00",
                "notice_period_days": 30,
                "terms": {"maintenance": "owner"},
                "agreement_reference": "renewal-contract",
            },
            format="json",
            **headers,
        )

    def test_cancellation_is_idempotent_and_records_one_event(self):
        created = self.create_lease_through_api()
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)
        payload = {"reason": "Tenant requested cancellation", "effective_date": date.today().isoformat()}

        first = self.client.post(
            f"/api/leases/{lease_id}/cancel/", payload, format="json", **headers
        )
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(
            f"/api/leases/{lease_id}/cancel/", payload, format="json", **headers
        )
        self.assertEqual(second.status_code, 200, second.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_CANCELLED)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED
            ).count(),
            1,
        )

    def test_future_contract_cannot_expire_early(self):
        future_end = (timezone.localdate() + timedelta(days=30)).isoformat()
        lease_id, headers = self.create_active_lease(end_date=future_end)
        url = f"/api/leases/{lease_id}/expire/"

        response = self.client.post(url, {}, format="json", **headers)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            response.data["error"],
            "Lease cannot expire before the active contract end date",
        )
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_ACTIVE)
        self.assertFalse(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
            ).exists()
        )

    def test_expiry_is_idempotent_and_records_one_event_on_contract_end_date(self):
        lease_id, headers = self.create_active_lease(end_date=timezone.localdate().isoformat())
        url = f"/api/leases/{lease_id}/expire/"
        first = self.client.post(url, {}, format="json", **headers)
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(url, {}, format="json", **headers)
        self.assertEqual(second.status_code, 200, second.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_EXPIRED)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
            ).count(),
            1,
        )

    def test_past_contract_end_date_can_expire(self):
        past_end = (timezone.localdate() - timedelta(days=1)).isoformat()
        lease_id, headers = self.create_active_lease(end_date=past_end)

        response = self.client.post(
            f"/api/leases/{lease_id}/expire/", {}, format="json", **headers
        )

        self.assertEqual(response.status_code, 200, response.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_EXPIRED)
        event = LeaseLifecycleEvent.objects.get(
            lease=lease, event_key=LeaseLifecycleEvent.EVENT_EXPIRED
        )
        self.assertEqual(event.effective_date, date.fromisoformat(past_end))

    def test_termination_is_idempotent_and_records_one_event(self):
        lease_id, headers = self.create_active_lease()
        payload = {"reason": "Mutual agreement", "effective_date": date.today().isoformat()}
        url = f"/api/leases/{lease_id}/terminate/"
        first = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(second.status_code, 200, second.data)
        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_TERMINATED)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_TERMINATED
            ).count(),
            1,
        )

    def test_notice_lifecycle_valid_transitions_and_invalid_retry(self):
        lease_id, headers = self.create_active_lease()
        today = date.today().isoformat()
        created = self.client.post(
            f"/api/leases/{lease_id}/notices/create/",
            {
                "notice_date": today,
                "effective_date": today,
                "notice_type": "termination",
                "reason": "Lease notice",
            },
            format="json",
            **headers,
        )
        self.assertEqual(created.status_code, 201, created.data)
        notice_id = created.data["data"]["id"]
        for target in ("issued", "effective", "completed"):
            response = self.client.post(
                f"/api/leases/notices/{notice_id}/transition/",
                {"status": target},
                format="json",
                **headers,
            )
            self.assertEqual(response.status_code, 200, response.data)
        repeated = self.client.post(
            f"/api/leases/notices/{notice_id}/transition/",
            {"status": "completed"},
            format="json",
            **headers,
        )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        invalid = self.client.post(
            f"/api/leases/notices/{notice_id}/transition/",
            {"status": "issued"},
            format="json",
            **headers,
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease_id=lease_id, event_key=f"notice:{notice_id}:completed"
            ).count(),
            1,
        )

    def test_renewal_overlap_is_rejected_and_confirmation_builds_version_chain(self):
        lease_id, headers = self.create_active_lease()
        created = self.create_renewal(lease_id, headers)
        self.assertEqual(created.status_code, 201, created.data)
        renewal_id = created.data["data"]["id"]

        overlap = self.client.post(
            f"/api/leases/{lease_id}/renewals/create/",
            {
                "start_date": "2027-09-01",
                "end_date": "2028-08-31",
                "rent_amount": "10500.00",
                "security_deposit": "10000.00",
            },
            format="json",
            **headers,
        )
        self.assertEqual(overlap.status_code, 400, overlap.data)

        confirm_url = f"/api/leases/renewals/{renewal_id}/confirm/"
        confirmed = self.client.post(confirm_url, {}, format="json", **headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        repeated = self.client.post(confirm_url, {}, format="json", **headers)
        self.assertEqual(repeated.status_code, 200, repeated.data)

        renewal = LeaseRenewal.objects.get(pk=renewal_id)
        self.assertEqual(renewal.status, LeaseRenewal.STATUS_CONFIRMED)
        successor = renewal.successor_version
        self.assertIsNotNone(successor)
        self.assertEqual(successor.version_number, 2)
        self.assertEqual(successor.predecessor.version_number, 1)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease_id=lease_id, event_key=f"renewal:{renewal_id}"
            ).count(),
            1,
        )

    def test_draft_renewal_cancellation_is_idempotent(self):
        lease_id, headers = self.create_active_lease()
        created = self.create_renewal(lease_id, headers)
        self.assertEqual(created.status_code, 201, created.data)
        renewal_id = created.data["data"]["id"]
        url = f"/api/leases/renewals/{renewal_id}/cancel/"
        first = self.client.post(url, {}, format="json", **headers)
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(url, {}, format="json", **headers)
        self.assertEqual(second.status_code, 200, second.data)
        renewal = LeaseRenewal.objects.get(pk=renewal_id)
        self.assertEqual(renewal.status, LeaseRenewal.STATUS_CANCELLED)
        self.assertIsNotNone(renewal.cancelled_at)
        self.assertEqual(
            LeaseLifecycleEvent.objects.filter(
                lease_id=lease_id, event_key=f"renewal:{renewal_id}:cancelled"
            ).count(),
            1,
        )

    def test_cancellation_rolls_back_when_lifecycle_event_write_fails(self):
        created = self.create_lease_through_api()
        self.assertEqual(created.status_code, 201, created.data)
        lease_id = created.data["data"]["id"]
        headers = self.authenticate(self.manager)

        with patch(
            "leasing.cancellation_service.append_lifecycle_event",
            side_effect=RuntimeError("event write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "event write failed"):
                self.client.post(
                    f"/api/leases/{lease_id}/cancel/",
                    {"reason": "Rollback test", "effective_date": date.today().isoformat()},
                    format="json",
                    **headers,
                )

        lease = Lease.objects.get(pk=lease_id)
        self.assertEqual(lease.status, Lease.STATUS_DRAFT)
        self.assertIsNone(lease.cancelled_at)
        self.assertFalse(
            LeaseLifecycleEvent.objects.filter(
                lease=lease, event_key=LeaseLifecycleEvent.EVENT_CANCELLED
            ).exists()
        )

    def test_renewal_confirmation_rolls_back_version_when_event_write_fails(self):
        lease_id, headers = self.create_active_lease()
        created = self.create_renewal(lease_id, headers)
        self.assertEqual(created.status_code, 201, created.data)
        renewal_id = created.data["data"]["id"]

        with patch(
            "leasing.renewal_service.append_lifecycle_event",
            side_effect=RuntimeError("event write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "event write failed"):
                self.client.post(
                    f"/api/leases/renewals/{renewal_id}/confirm/",
                    {},
                    format="json",
                    **headers,
                )

        renewal = LeaseRenewal.objects.get(pk=renewal_id)
        self.assertEqual(renewal.status, LeaseRenewal.STATUS_DRAFT)
        self.assertIsNone(renewal.successor_version_id)
        self.assertFalse(
            LeaseContractVersion.objects.filter(
                lease_id=lease_id, version_number=2
            ).exists()
        )
        self.assertFalse(
            LeaseLifecycleEvent.objects.filter(
                lease_id=lease_id, event_key=f"renewal:{renewal_id}"
            ).exists()
        )

    def test_cross_workspace_header_is_rejected(self):
        outsider = create_user_account(
            "lease-api-header-outsider@example.com",
            "StrongPassword123!",
            "StrongPassword123!",
            "Lease API Header Workspace",
        )
        response = self.client.post(
            "/api/leases/create/",
            self.lease_payload(),
            format="json",
            **self.authenticate(self.owner, outsider.owned_workspaces.get()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Lease.objects.filter(occupancy=self.occupancy).exists())
