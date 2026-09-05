from django.contrib import admin
from .models import Property, PropertyImage


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1


class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "property_type", "city", "state", "is_active", "is_listed", "created_at")
    list_filter = ("property_type", "city", "state", "is_active", "is_listed")
    search_fields = ("name", "city", "state", "owner__email")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [PropertyImageInline]


class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ("property", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("property__name",)
    autocomplete_fields = ("property",)
    readonly_fields = ("created_at",)


# Intentionally not registered: forced RLS has no unrestricted Admin context.
