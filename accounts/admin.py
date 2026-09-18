from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction

from .models import User, UserProfile, Staff
from .services import set_account_active


class UserAdmin(BaseUserAdmin):

    model = User

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

    readonly_fields = ("date_joined", "email_verified_at")

    fieldsets = (
        ("User Info", {
            "fields": ("email", "password")
        }),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("Account Info", {
            "fields": ("phone", "email_verified", "email_verified_at")
        }),
        ("Important Dates", {
            "fields": ("date_joined",)
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2"),
        }),
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                previous = User.objects.get(pk=obj.pk)
                if previous.is_active and not obj.is_active:
                    set_account_active(obj, False)
            super().save_model(request, obj, form, change)


class UserProfileAdmin(admin.ModelAdmin):

    list_display = ("user", "city", "state")

    search_fields = ("user__email", "city", "state")

    list_filter = ("city", "state")


admin.site.site_header = "AjnihaStay Admin"
admin.site.site_title = "AjnihaStay"
admin.site.index_title = "Welcome to AjnihaStay Dashboard"
