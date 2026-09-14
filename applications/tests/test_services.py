from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from applications.models import Applicant, Application, ApplicationEvent
from applications.services import (
    approve_application,
    create_applicant,
    create_application,
    get_application_history,
    reject_application,
    review_application,
    submit_application,
    withdraw_application,
)
from properties.models import Property
from unit.models import SubUnit, Unit
from workspaces.models import Membership, Workspace


class ApplicationServiceTests(TestCase):
    def setUp(self):
        password = "StrongPass123!"
        self.owner = User.objects.create_user("application-owner@example.com", password)
        self.other_owner = User.objects.create_user("application-other@example.com", password)
        self.inactive = User.objects.create_user("application-inactive@example.com", password)
        self.inactive.is_active = False
        self.inactive.save(update_fields=["is_active"])

        self.workspace = Workspace.objects.create(
            name="Application Workspace",
            slug="application-workspace",
            owner=self.owner,
        )
        self.other_workspace = Workspace.objects.create(
            name="Other Application Workspace",
            slug="other-application-workspace",
            owner=self.other_owner,
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        Membership.objects.create(workspace=self.other_workspace, user=self.other_owner, role="owner")

        self.property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Application Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110001",
        )
        self.other_property = Property.objects.create(
            owner=self.other_owner,
            workspace=self.other_workspace,
            name="Other Application Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110002",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type="room",
            unit_number="101",
            rent=Decimal("10000.00"),
        )
        self.other_unit = Unit.objects.create(
            property=self.other_property,
            unit_type="room",
            unit_number="201",
            rent=Decimal("9000.00"),
        )
        self.subunit = SubUnit.objects.create(
            unit=self.unit,
            subunit_number="A",
            rent=Decimal("5000.00"),
        )
        self.other_subunit = SubUnit.objects.create(
            unit=self.other_unit,
            subunit_number="A",
            rent=Decimal("4500.00"),
        )
        self.applicant = Applicant.objects.create(
            workspace=self.workspace,
            full_name="Application Applicant",
            phone="9999999999",
            email="applicant@example.com",
            address="Delhi",
        )

    def applicant_data(self, **overrides):
        data = {
            "full_name": self.applicant.full_name,
            "phone": self.applicant.phone,
            "email": self.applicant.email,
            "address": self.applicant.address,
        }
        data.update(overrides)
        return data

    def application_data(self, **overrides):
        data = {
            "applicant": self.applicant.id,
            "property": self.property.id,
            "unit": self.unit.id,
            "subunit": self.subunit.id,
            "requested_check_in_date": date(2026, 10, 1),
            "requested_check_out_date": date(2027, 9, 30),
        }
        data.update(overrides)
        return data

    def make_application(self, **overrides):
        return create_application(self.workspace, self.application_data(**overrides), self.owner)

    def test_create_applicant_deduplicates_same_workspace_identity(self):
        created = create_applicant(
            self.workspace,
            self.applicant_data(phone=self.applicant.phone, email="APPlicant@EXAMPLE.com"),
            self.owner,
        )
        self.assertEqual(created.pk, self.applicant.pk)
        self.assertEqual(Applicant.objects.filter(workspace=self.workspace).count(), 1)

    def test_create_applicant_rejects_ambiguous_identity_match(self):
        second = Applicant.objects.create(
            workspace=self.workspace,
            full_name="Second Applicant",
            phone="8888888888",
            email="second@example.com",
        )
        with self.assertRaisesMessage(ValidationError, "Applicant identity match is ambiguous"):
            create_applicant(
                self.workspace,
                {
                    "full_name": "Ambiguous",
                    "phone": self.applicant.phone,
                    "email": second.email,
                },
                self.owner,
            )

    def test_create_applicant_never_matches_other_workspace(self):
        other = Applicant.objects.create(
            workspace=self.other_workspace,
            full_name="Other Applicant",
            phone="7777777777",
            email="shared@example.com",
        )
        created = create_applicant(
            self.workspace,
            {
                "full_name": "Local Applicant",
                "phone": other.phone,
                "email": other.email,
            },
            self.owner,
        )
        self.assertNotEqual(created.workspace_id, other.workspace_id)
        self.assertNotEqual(created.pk, other.pk)

    def test_create_application_rejects_cross_workspace_applicant(self):
        other_applicant = Applicant.objects.create(
            workspace=self.other_workspace,
            full_name="Other Applicant",
            phone="7777777777",
        )
        with self.assertRaisesMessage(ValidationError, "Applicant not found"):
            create_application(
                self.workspace,
                self.application_data(applicant=other_applicant.id),
                self.owner,
            )

    def test_create_application_rejects_cross_workspace_property(self):
        with self.assertRaisesMessage(ValidationError, "Property not found"):
            create_application(
                self.workspace,
                self.application_data(property=self.other_property.id, unit=None, subunit=None),
                self.owner,
            )

    def test_create_application_rejects_unit_from_wrong_property(self):
        with self.assertRaisesMessage(ValidationError, "Unit not found"):
            create_application(
                self.workspace,
                self.application_data(unit=self.other_unit.id, subunit=None),
                self.owner,
            )

    def test_create_application_rejects_subunit_without_unit(self):
        with self.assertRaisesMessage(ValidationError, "SubUnit requires a Unit"):
            create_application(
                self.workspace,
                self.application_data(unit=None, subunit=self.subunit.id),
                self.owner,
            )

    def test_create_application_rejects_subunit_from_wrong_unit(self):
        with self.assertRaisesMessage(ValidationError, "SubUnit not found"):
            create_application(
                self.workspace,
                self.application_data(subunit=self.other_subunit.id),
                self.owner,
            )

    def test_create_application_rejects_invalid_date_order(self):
        with self.assertRaisesMessage(ValidationError, "Requested check-out date cannot be before check-in date"):
            create_application(
                self.workspace,
                self.application_data(
                    requested_check_in_date=date(2026, 10, 10),
                    requested_check_out_date=date(2026, 10, 9),
                ),
                self.owner,
            )

    def test_create_application_requires_authenticated_actor(self):
        with self.assertRaisesMessage(ValidationError, "Authenticated actor required"):
            create_application(self.workspace, self.application_data(), None)

    def test_create_application_rejects_inactive_actor(self):
        with self.assertRaisesMessage(ValidationError, "Actor account is inactive"):
            create_application(self.workspace, self.application_data(), self.inactive)

    def test_duplicate_active_application_is_rejected(self):
        self.make_application()
        with self.assertRaisesMessage(ValidationError, "An active application already exists"):
            self.make_application()

    def test_duplicate_scope_is_property_local(self):
        self.make_application()
        second_property = Property.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            name="Second Property",
            property_type="pg",
            address="Delhi",
            city="Delhi",
            state="Delhi",
            pincode="110003",
        )
        application = self.make_application(property=second_property.id, unit=None, subunit=None)
        self.assertEqual(application.property_id, second_property.id)

    def test_submit_creates_one_history_event(self):
        application = self.make_application()
        updated = submit_application(self.workspace, application.id, self.owner)
        self.assertEqual(updated.status, Application.STATUS_SUBMITTED)
        events = ApplicationEvent.objects.filter(application=application).order_by("id")
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.from_status, Application.STATUS_DRAFT)
        self.assertEqual(event.to_status, Application.STATUS_SUBMITTED)
        self.assertEqual(event.actor_id, self.owner.id)

    def test_repeated_submit_is_idempotent_without_duplicate_history(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        updated = submit_application(self.workspace, application.id, self.owner)
        self.assertEqual(updated.status, Application.STATUS_SUBMITTED)
        self.assertEqual(ApplicationEvent.objects.filter(application=application).count(), 1)

    def test_invalid_lifecycle_transition_is_rejected(self):
        application = self.make_application()
        with self.assertRaisesMessage(ValidationError, "Invalid application transition"):
            approve_application(self.workspace, application.id, self.owner)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.STATUS_DRAFT)
        self.assertFalse(ApplicationEvent.objects.filter(application=application).exists())

    def test_review_requires_submitted_status(self):
        application = self.make_application()
        with self.assertRaisesMessage(ValidationError, "Invalid application transition"):
            review_application(self.workspace, application.id, self.owner)

    def test_reject_requires_reason(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        review_application(self.workspace, application.id, self.owner)
        with self.assertRaisesMessage(ValidationError, "Rejection reason required"):
            reject_application(self.workspace, application.id, self.owner, "   ")
        application.refresh_from_db()
        self.assertEqual(application.status, Application.STATUS_UNDER_REVIEW)

    def test_reject_persists_reason_and_terminal_state(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        review_application(self.workspace, application.id, self.owner)
        reject_application(self.workspace, application.id, self.owner, "Income criteria not met")
        application.refresh_from_db()
        self.assertEqual(application.status, Application.STATUS_REJECTED)
        self.assertEqual(application.rejection_reason, "Income criteria not met")
        self.assertIsNotNone(application.decided_at)
        self.assertEqual(ApplicationEvent.objects.filter(application=application).count(), 3)

    def test_withdrawn_application_is_terminal(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        withdraw_application(self.workspace, application.id, self.owner, "Applicant changed plans")
        application.refresh_from_db()
        self.assertEqual(application.status, Application.STATUS_WITHDRAWN)
        self.assertEqual(application.withdrawal_reason, "Applicant changed plans")
        with self.assertRaisesMessage(ValidationError, "Invalid application transition"):
            review_application(self.workspace, application.id, self.owner)

    def test_approved_application_is_terminal(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        review_application(self.workspace, application.id, self.owner)
        approve_application(self.workspace, application.id, self.owner)
        with self.assertRaisesMessage(ValidationError, "Invalid application transition"):
            withdraw_application(self.workspace, application.id, self.owner, "Too late")

    def test_history_is_immutable(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        event = ApplicationEvent.objects.get(application=application)

        with self.assertRaisesMessage(ValidationError, "Application history is immutable"):
            ApplicationEvent.objects.filter(pk=event.pk).update(reason="tampered")
        with self.assertRaisesMessage(ValidationError, "Application history is immutable"):
            ApplicationEvent.objects.filter(pk=event.pk).delete()
        event.reason = "tampered"
        with self.assertRaisesMessage(ValidationError, "Application history is immutable"):
            event.save()

        with self.assertRaisesMessage(ValidationError, "Application history must be appended"):
            ApplicationEvent.objects.bulk_create([event])

    def test_lifecycle_queryset_update_is_blocked(self):
        application = self.make_application()
        with self.assertRaisesMessage(ValidationError, "Application lifecycle fields must be changed through the application service"):
            Application.objects.filter(pk=application.pk).update(status=Application.STATUS_SUBMITTED)

    def test_lifecycle_bulk_update_is_blocked(self):
        application = self.make_application()
        application.status = Application.STATUS_SUBMITTED
        with self.assertRaisesMessage(ValidationError, "Application lifecycle fields must be changed through the application service"):
            Application.objects.bulk_update([application], ["status"])

    def test_direct_lifecycle_save_is_blocked(self):
        application = self.make_application()
        application.status = Application.STATUS_SUBMITTED
        with self.assertRaisesMessage(ValidationError, "Application lifecycle fields must be changed through the application service"):
            application.save(update_fields=["status"])

    def test_new_application_cannot_start_non_draft(self):
        with self.assertRaisesMessage(ValidationError, "New applications must start in draft status"):
            Application.objects.create(
                workspace=self.workspace,
                applicant=self.applicant,
                property=self.property,
                status=Application.STATUS_SUBMITTED,
                created_by=self.owner,
                updated_by=self.owner,
            )

    def test_cross_workspace_application_lookup_isolated(self):
        application = self.make_application()
        with self.assertRaisesMessage(ValidationError, "Application not found"):
            approve_application(self.other_workspace, application.id, self.other_owner)

    def test_history_lookup_is_workspace_scoped(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        self.assertEqual(get_application_history(self.workspace, application.id).count(), 1)
        with self.assertRaisesMessage(ValidationError, "Application not found"):
            list(get_application_history(self.other_workspace, application.id))

    def test_approval_has_no_tenant_occupancy_or_financial_side_effects(self):
        application = self.make_application()

        with patch("applications.services.ApplicationEvent.append", wraps=ApplicationEvent.append) as append:
            submit_application(self.workspace, application.id, self.owner)
            review_application(self.workspace, application.id, self.owner)
            approved = approve_application(self.workspace, application.id, self.owner)

        self.assertEqual(approved.status, Application.STATUS_APPROVED)
        self.assertTrue(append.called)

        from payments.models import Invoice, Payment
        from tenant.models import Charge, Occupancy, Tenant

        self.assertFalse(Tenant.objects.filter(workspace=self.workspace).exists())
        self.assertFalse(Occupancy.objects.exists())
        self.assertFalse(Charge.objects.exists())
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_application_history_returns_ordered_transitions(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        review_application(self.workspace, application.id, self.owner)
        approve_application(self.workspace, application.id, self.owner)
        transitions = list(
            get_application_history(self.workspace, application.id).values_list(
                "from_status", "to_status"
            )
        )
        self.assertEqual(
            transitions,
            [
                (Application.STATUS_DRAFT, Application.STATUS_SUBMITTED),
                (Application.STATUS_SUBMITTED, Application.STATUS_UNDER_REVIEW),
                (Application.STATUS_UNDER_REVIEW, Application.STATUS_APPROVED),
            ],
        )

    def test_manual_duplicate_event_is_blocked_by_unique_key(self):
        application = self.make_application()
        submit_application(self.workspace, application.id, self.owner)
        event = ApplicationEvent.objects.get(application=application)
        duplicate = ApplicationEvent(
            workspace=self.workspace,
            application=application,
            applicant=self.applicant,
            from_status=Application.STATUS_DRAFT,
            to_status=Application.STATUS_SUBMITTED,
            actor=self.owner,
            occurred_at=event.occurred_at,
            reason="duplicate",
            metadata={},
            event_key=event.event_key,
        )
        duplicate._allow_event_creation = True
        with self.assertRaises(IntegrityError):
            duplicate.save(force_insert=True)

    def test_create_application_maps_integrity_race_to_validation_error(self):
        with patch.object(Application, "save", side_effect=IntegrityError("duplicate active application")):
            with self.assertRaisesMessage(ValidationError, "An active application already exists"):
                self.make_application()
