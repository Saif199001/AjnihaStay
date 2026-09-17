from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, Staff


class UserAdmin(BaseUserAdmin):

    model = User

    list_display = (
        "email",
        "is_active",
        "is_staff",
        "is_active_account",
        "date_joined",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = ("email", "phone")

    ordering = ("-date_joined",)

    readonly_fields = ("date_joined",)

    fieldsets = (
        ("User Info", {
            "fields": ("email", "password")
        }),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("Account Info", {
            "fields": ("phone", "is_active_account")
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


class UserProfileAdmin(admin.ModelAdmin):

    list_display = ("user", "city", "state")

    search_fields = ("user__email", "city", "state")

    list_filter = ("city", "state")


class StaffAdmin(admin.ModelAdmin):

    list_display = ("user", "owner", "is_active", "created_at")

    list_filter = ("is_active",)

    search_fields = ("user__email", "owner__email")

    autocomplete_fields = ("owner", "user")

    readonly_fields = ("created_at",)


admin.site.register(User, UserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Staff, StaffAdmin)

admin.site.site_header = "AjnihaStay Admin"
admin.site.site_title = "AjnihaStay"
admin.site.index_title = "Welcome to AjnihaStay Dashboard"
