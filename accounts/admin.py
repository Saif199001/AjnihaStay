from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, Staff


# 🔥 Custom User Admin
class UserAdmin(BaseUserAdmin):

    model = User

    list_display = (
        "email",
        "role",
        "is_active",
        "is_staff",
        "is_active_account",
        "date_joined",
    )

    list_filter = (
        "role",
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
        ("Role Info", {
            "fields": ("role", "phone", "is_active_account")
        }),
        ("Important Dates", {
            "fields": ("date_joined",)
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role"),
        }),
    )


# 🔥 User Profile Admin
class UserProfileAdmin(admin.ModelAdmin):

    list_display = ("user", "city", "state")

    search_fields = ("user__email", "city", "state")

    list_filter = ("city", "state")


# 🔥 Staff Admin
class StaffAdmin(admin.ModelAdmin):

    list_display = ("user", "owner", "role", "is_active", "created_at")

    list_filter = ("role", "is_active")

    search_fields = ("user__email", "owner__email")

    autocomplete_fields = ("owner", "user")

    readonly_fields = ("created_at",)


# 🔥 Register Models
admin.site.register(User, UserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Staff, StaffAdmin)

# 🔥 Admin Panel Branding
admin.site.site_header = "AjnihaStay Admin"
admin.site.site_title = "AjnihaStay"
admin.site.index_title = "Welcome to AjnihaStay Dashboard"