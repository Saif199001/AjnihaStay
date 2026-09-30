from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import User, UserProfile
from .services import set_account_active


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    PLATFORM_PRIVILEGE_FIELDS = frozenset(
        {"is_staff", "is_superuser", "groups", "user_permissions"}
    )

    list_display = (
        "email",
        "is_active",
        "is_staff",
        "email_verified",
        "date_joined",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "email_verified",
    )

    search_fields = ("email", "phone")
    ordering = ("-date_joined",)
    readonly_fields = ("date_joined", "email_verified", "email_verified_at")

    fieldsets = (
        ("User Info", {"fields": ("email", "password")}),
        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
        ("Account Info", {"fields": ("phone", "email_verified", "email_verified_at")}),
        ("Important Dates", {"fields": ("date_joined",)}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2"),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = set(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly.update(self.PLATFORM_PRIVILEGE_FIELDS)
        return tuple(readonly)

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                previous = User.objects.get(pk=obj.pk)

                if not request.user.is_superuser:
                    for field in ("is_staff", "is_superuser"):
                        if getattr(previous, field) != getattr(obj, field):
                            raise PermissionDenied(
                                "Platform privilege changes require superuser authority."
                            )

                if previous.is_active != obj.is_active:
                    locked_user = set_account_active(obj, obj.is_active)
                    obj.is_active = locked_user.is_active

            super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        if not request.user.is_superuser:
            for field in ("groups", "user_permissions"):
                if field in form.changed_data:
                    raise PermissionDenied(
                        "Platform privilege changes require superuser authority."
                    )
        super().save_related(request, form, formsets, change)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "state")
    search_fields = ("user__email", "city", "state")
    list_filter = ("city", "state")


admin.site.site_header = "AjnihaStay Admin"
admin.site.site_title = "AjnihaStay"
admin.site.index_title = "Welcome to AjnihaStay Dashboard"
