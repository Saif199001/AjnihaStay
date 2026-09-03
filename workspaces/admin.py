from django.contrib import admin

from .models import Membership, Workspace


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "created_at")
    search_fields = ("name", "slug", "owner__email")
    list_filter = ("is_active",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "role", "is_active", "created_at")
    search_fields = ("workspace__name", "user__email")
    list_filter = ("role", "is_active")
