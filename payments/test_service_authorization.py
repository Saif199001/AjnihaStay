from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.models import User
from workspaces.models import Membership, Workspace

from .authorization import require_mutation_permission


class FinancialMutationAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("b5-owner@example.com", "StrongPass123!")
        self.admin = User.objects.create_user("b5-admin@example.com", "StrongPass123!")
        self.manager = User.objects.create_user("b5-manager@example.com", "StrongPass123!")
        self.staff = User.objects.create_user("b5-staff@example.com", "StrongPass123!")
        self.inactive_manager = User.objects.create_user("b5-inactive@example.com", "StrongPass123!")
        self.non_member = User.objects.create_user("b5-nonmember@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="B5 Workspace", slug="b5-workspace", owner=self.owner
        )
        Membership.objects.create(workspace=self.workspace, user=self.owner, role=Membership.ROLE_OWNER)
        Membership.objects.create(workspace=self.workspace, user=self.admin, role=Membership.ROLE_ADMIN)
        Membership.objects.create(workspace=self.workspace, user=self.manager, role=Membership.ROLE_MANAGER)
        Membership.objects.create(workspace=self.workspace, user=self.staff, role=Membership.ROLE_STAFF)
        Membership.objects.create(
            workspace=self.workspace,
            user=self.inactive_manager,
            role=Membership.ROLE_MANAGER,
            is_active=False,
        )

    def test_owner_admin_manager_are_allowed(self):
        for user in (self.owner, self.admin, self.manager):
            with self.subTest(user=user):
                require_mutation_permission(user, self.workspace)

    def test_staff_inactive_nonmember_and_none_are_denied(self):
        for user in (self.staff, self.inactive_manager, self.non_member, None):
            with self.subTest(user=user):
                with self.assertRaises(PermissionDenied):
                    require_mutation_permission(user, self.workspace)

    def test_shared_guard_is_used_by_all_financial_mutation_services(self):
        cases = [
            ("payments.services", "create_invoice", (self.owner, self.workspace, {})),
            ("payments.services", "record_payment", (self.owner, self.workspace, {})),
            ("payments.allocation_service", "allocate_payment", (self.owner, self.workspace, 1, [])),
            ("payments.advance_credit_service", "create_advance_credit", (self.owner, self.workspace, {})),
            ("payments.advance_credit_service", "apply_advance_credit", (self.owner, self.workspace, {})),
            ("payments.billing_service", "create_billing_schedule", (self.owner, self.workspace, {})),
            ("payments.billing_service", "update_billing_schedule", (self.owner, self.workspace, 1, {})),
            ("payments.charge_generation_service", "generate_charge_from_schedule", (self.owner, self.workspace, 1, None)),
            ("payments.adjustment_service", "create_financial_adjustment", (self.owner, self.workspace, {})),
        ]
        for module_name, function_name, args in cases:
            with self.subTest(function=f"{module_name}.{function_name}"), patch(
                f"{module_name}.require_mutation_permission"
            ) as guard:
                module = __import__(module_name, fromlist=[function_name])
                try:
                    getattr(module, function_name)(*args)
                except Exception:
                    pass
                guard.assert_called_once_with(self.owner, self.workspace)
