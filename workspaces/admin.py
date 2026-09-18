from django import forms
from django.contrib import admin

from .models import Membership, Workspace


class MembershipAdminForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["workspace"].disabled = True
            self.fields["user"].disabled = True
        if self.instance and self.instance.pk and self.instance.role == Membership.ROLE_OWNER:
            self.fields["role"].disabled = True
            self.fields["is_active"].disabled = True
        else:
            self.fields["role"].choices = [
                (Membership.ROLE_ADMIN, "Admin"),
                (Membership.ROLE_MANAGER, "Manager"),
                (Membership.ROLE_VIEWER, "Viewer"),
            ]

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.instance and self.instance.pk and self.instance.role == Membership.ROLE_OWNER:
            return Membership.ROLE_OWNER
        if role == Membership.ROLE_OWNER:
            raise forms.ValidationError(
                "Owner role can only be assigned through the ownership transfer workflow."
            )
        return role

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if self.instance and self.instance.pk and self.instance.role == Membership.ROLE_OWNER:
            return True
        return is_active


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "created_at")
    search_fields = ("name", "slug", "owner__email")
    list_filter = ("is_active",)
    readonly_fields = ("owner", "slug", "is_active", "created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    form = MembershipAdminForm
    list_display = ("workspace", "user", "role", "is_active", "created_at")
    search_fields = ("workspace__name", "user__email")
    list_filter = ("role", "is_active")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
