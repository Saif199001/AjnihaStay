from django.contrib import admin
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import User
from properties.models import Property
from tenant.models import Tenant
from unit.models import SubUnit, Unit
from payments.models import Invoice, Payment

from .models import Membership, Workspace
from .permissions import WorkspaceStaffPermission


class WorkspaceRLSAdminArchitectureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("rls-admin-audit@example.com", "StrongPass123!")
        self.workspace = Workspace.objects.create(
            name="RLS Admin Audit",
            slug="rls-admin-audit",
            owner=self.user,
        )
        Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")

    def test_forced_rls_protected_domain_models_are_not_registered_in_admin(self):
        protected_models = (Property, Unit, SubUnit, Tenant, Invoice, Payment)
        for model in protected_models:
            self.assertFalse(
                admin.site.is_registered(model),
                f"{model._meta.label} must not be exposed through unrestricted Django Admin",
            )

    def test_workspace_permission_binds_selected_workspace(self):
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.user = self.user

        permission = WorkspaceStaffPermission()
        self.assertTrue(permission.has_permission(request, object()))
        self.assertEqual(request.workspace.id, self.workspace.id)
        self.assertEqual(request.workspace_membership.workspace_id, self.workspace.id)
