from django.contrib import admin
from .models import Unit, SubUnit, UnitImage


class SubUnitInline(admin.TabularInline):
    model = SubUnit
    extra = 1


class UnitImageInline(admin.TabularInline):
    model = UnitImage
    extra = 1


class UnitAdmin(admin.ModelAdmin):
    list_display = ("unit_number", "property", "unit_type", "rent", "capacity", "is_active", "is_available_for_public", "is_occupied_status")
    list_filter = ("unit_type", "is_active", "is_available_for_public", "property__city")
    search_fields = ("unit_number", "property__name")
    autocomplete_fields = ("property",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [SubUnitInline, UnitImageInline]

    def is_occupied_status(self, obj):
        return obj.is_occupied()

    is_occupied_status.boolean = True
    is_occupied_status.short_description = "Occupied"


class SubUnitAdmin(admin.ModelAdmin):
    list_display = ("subunit_number", "unit", "rent", "is_active", "is_occupied_status")
    list_filter = ("is_active",)
    search_fields = ("subunit_number", "unit__unit_number")
    autocomplete_fields = ("unit",)
    readonly_fields = ("created_at",)

    def is_occupied_status(self, obj):
        return obj.is_occupied()

    is_occupied_status.boolean = True
    is_occupied_status.short_description = "Occupied"


class UnitImageAdmin(admin.ModelAdmin):
    list_display = ("unit", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("unit__unit_number",)
    autocomplete_fields = ("unit",)
    readonly_fields = ("created_at",)


# Intentionally not registered: forced RLS has no unrestricted Admin context.
