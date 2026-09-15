from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from leasing.lifecycle_event_service import append_lifecycle_event
from leasing.lifecycle_models import LeaseContractVersion, LeaseLifecycleEvent, LeaseNotice, LeaseRenewal
from leasing.lease_service import create_lease, transition_lease
from leasing.models import Lease
from leasing.notice_service import create_notice
from leasing.renewal_service import cancel_renewal, confirm_renewal, create_renewal
from properties.models import Property
from tenant.models import Occupancy, Tenant
from unit.models import Unit
from workspaces.models import Membership, Workspace


class P15FinalGapTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="p15-final-owner@example.com", password="pass")
        self.manager = User.objects.create_user(email="p15-final-manager@example.com", password="pass")
        self.workspace = Workspace.objects.create(
            name="P15 Final Workspace", slug="p15-final-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner", is_active=True)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role="manager", is_active=True)
        property_obj = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="P15 Final Property",
            property_type="flat",
            address="Address",
            city="Lucknow",
            state="UP",
            pincode="226001",
        )
        unit = Unit.objects.create(
            property=property_obj,
            unit_type="flat",
            unit_number="101",
            rent=Decimal("12000.00"),
        )
        tenant = Tenant.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            full_name="P15 Final Tenant",
            phone="9999999997",
            email="p15-final-tenant@example.com",
            permanent_address="Lucknow",
        )
        occupancy = Occupancy.objects.create(
            tenant=tenant,
            unit=unit,
            rent=Decimal("12000.00"),
            security_deposit=Decimal("24000.00"),
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 12, 31),
            next_due_date=date(2026, 1, 1),
            is_active=True,
        )
        lease = create_lease(
            self.manager,
            self.workspace,
            {
                "occupancy": occupancy,
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "rent_amount": Decimal("12000.00"),
                "security_deposit": Decimal("24000.00"),
            },
        )
        transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_PENDING_SIGNATURE)
        self.lease = transition_lease(self.manager, self.workspace, lease.id, Lease.STATUS_ACTIVE)

    def renewal_data(self, **overrides):
        data = {
            "start_date": date(2027, 1, 1),
            "end_date": date(2027, 12, 31),
            "rent_amount": Decimal("13500.00"),
            "security_deposit": Decimal("27000.00"),
        }
        data.update(overrides)
        return data

    def test_lease_bulk_update_status_is_rejected(self):
        lease = Lease.objects.get(pk=self.lease.pk)
        lease.status = Lease.STATUS_EXPIRED
        with self.assertRaises(ValidationError):
            Lease.objects.bulk_update([lease], ["status"])
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.STATUS_ACTIVE)

    def test_notice_bulk_create_is_rejected(self):
        notice = LeaseNotice(
            workspace=self.workspace,
            lease=self.lease,
            notice_date=date(2026, 9, 1),
            effective_date=date(2026, 10, 1),
            notice_type=LeaseNotice.TYPE_NON_RENEWAL,
            reason="Bulk create bypass test",
            created_by=self.manager,
        )
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.bulk_create([notice])

    def test_notice_bulk_update_status_is_rejected(self):
        notice = create_notice(
            self.manager,
            self.workspace,
            self.lease.id,
            notice_date=date(2026, 9, 1),
            effective_date=date(2026, 10, 1),
            notice_type=LeaseNotice.TYPE_NON_RENEWAL,
            reason="Bulk update bypass test",
        )
        notice.status = LeaseNotice.STATUS_ISSUED
        with self.assertRaises(ValidationError):
            LeaseNotice.objects.bulk_update([notice], ["status"])
        notice.refresh_from_db()
        self.assertEqual(notice.status, LeaseNotice.STATUS_DRAFT)

    def test_confirmed_renewal_bulk_update_is_rejected(self):
        renewal = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())
        confirm_renewal(self.manager, self.workspace, renewal.id)
        renewal.refresh_from_db()
        renewal.rent_amount = Decimal("99999.00")
        with self.assertRaises(ValidationError):
            LeaseRenewal.objects.bulk_update([renewal], ["rent_amount"])
        renewal.refresh_from_db()
        self.assertEqual(renewal.rent_amount, Decimal("13500.00"))

    def test_contract_version_bulk_update_is_rejected(self):
        version = LeaseContractVersion.objects.get(lease=self.lease, version_number=1)
        version.rent_amount = Decimal("99999.00")
        with self.assertRaises(ValidationError):
            LeaseContractVersion.objects.bulk_update([version], ["rent_amount"])
        version.refresh_from_db()
        self.assertEqual(version.rent_amount, Decimal("12000.00"))

    def test_lifecycle_event_bulk_update_is_rejected(self):
        event = append_lifecycle_event(
            lease=self.lease,
            event_type=LeaseLifecycleEvent.EVENT_NOTICE,
            actor=self.manager,
            effective_date=date(2026, 10, 1),
            metadata={"test": True},
            event_key="p15-final-bulk-update-test",
        )
        event.metadata = {"test": False}
        with self.assertRaises(ValidationError):
            LeaseLifecycleEvent.objects.bulk_update([event], ["metadata"])
        event.refresh_from_db()
        self.assertEqual(event.metadata, {"test": True})

    def test_cancelled_renewal_does_not_block_same_contract_period(self):
        first = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())
        cancel_renewal(self.manager, self.workspace, first.id)
        first.refresh_from_db()

        second = create_renewal(self.manager, self.workspace, self.lease.id, self.renewal_data())

        self.assertEqual(first.status, LeaseRenewal.STATUS_CANCELLED)
        self.assertEqual(second.status, LeaseRenewal.STATUS_DRAFT)
        self.assertEqual(second.renewal_number, 2)
