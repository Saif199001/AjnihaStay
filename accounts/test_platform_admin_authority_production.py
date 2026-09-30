from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .admin import UserAdmin


User = get_user_model()


class UserAdminPlatformAuthorityProductionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = UserAdmin(User, None)
        self.staff_admin = User.objects.create_user(
            email="staff-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=False,
            email_verified=True,
        )
        self.platform_admin = User.objects.create_user(
            email="platform-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
            email_verified=True,
        )
        self.target = User.objects.create_user(
            email="target@example.com",
            password="StrongPass123!",
            is_staff=False,
            is_superuser=False,
            email_verified=True,
        )

    def request_for(self, user):
        request = self.factory.get("/admin/accounts/user/")
        request.user = user
        return request

    def test_non_superuser_cannot_edit_platform_privilege_fields(self):
        readonly = set(
            self.admin.get_readonly_fields(
                self.request_for(self.staff_admin),
                self.target,
            )
        )

        self.assertTrue(
            {
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            }.issubset(readonly)
        )
        self.assertNotIn("is_active", readonly)

    def test_superuser_can_edit_platform_privilege_fields(self):
        readonly = set(
            self.admin.get_readonly_fields(
                self.request_for(self.platform_admin),
                self.target,
            )
        )

        self.assertTrue(
            {"date_joined", "email_verified", "email_verified_at"}.issubset(readonly)
        )
        self.assertFalse(
            {
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            }.intersection(readonly)
        )

    def test_non_superuser_forged_staff_change_is_blocked(self):
        request = self.request_for(self.staff_admin)
        self.target.is_staff = True

        with self.assertRaises(PermissionDenied):
            self.admin.save_model(
                request,
                self.target,
                SimpleNamespace(),
                change=True,
            )

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)

    def test_non_superuser_forged_superuser_change_is_blocked(self):
        request = self.request_for(self.staff_admin)
        self.target.is_superuser = True

        with self.assertRaises(PermissionDenied):
            self.admin.save_model(
                request,
                self.target,
                SimpleNamespace(),
                change=True,
            )

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_superuser)

    def test_non_superuser_group_change_is_blocked(self):
        request = self.request_for(self.staff_admin)
        form = SimpleNamespace(changed_data=["groups"])

        with self.assertRaises(PermissionDenied):
            self.admin.save_related(request, form, [], True)

    def test_non_superuser_permission_change_is_blocked(self):
        request = self.request_for(self.staff_admin)
        form = SimpleNamespace(changed_data=["user_permissions"])

        with self.assertRaises(PermissionDenied):
            self.admin.save_related(request, form, [], True)

    def test_superuser_can_save_platform_privilege_changes(self):
        request = self.request_for(self.platform_admin)
        self.target.is_staff = True
        self.target.is_superuser = True

        self.admin.save_model(
            request,
            self.target,
            SimpleNamespace(),
            change=True,
        )

        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)
        self.assertTrue(self.target.is_superuser)

    def test_non_superuser_can_still_change_account_active_state_through_service(self):
        request = self.request_for(self.staff_admin)
        self.target.is_active = False

        self.admin.save_model(
            request,
            self.target,
            SimpleNamespace(),
            change=True,
        )

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
