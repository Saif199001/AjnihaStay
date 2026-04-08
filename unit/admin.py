from django.contrib import admin
from .models import Unit, SubUnit, UnitImage


# 🔥 SubUnit Inline (Unit page पर beds दिखेंगे)
class SubUnitInline(admin.TabularInline):
    model = SubUnit
    extra = 1


# 🔥 Unit Image Inline
class UnitImageInline(admin.TabularInline):
    model = UnitImage
    extra = 1


# 🔥 Unit Admin
class UnitAdmin(admin.ModelAdmin):

    list_display = (
        "unit_number",
        "property",
        "unit_type",
        "rent",
        "capacity",
        "is_active",
        "is_available_for_public",
        "is_occupied_status",
    )

    list_filter = (
        "unit_type",
        "is_active",
        "is_available_for_public",
        "property__city",
    )

    search_fields = (
        "unit_number",
        "property__name",
    )

    autocomplete_fields = ("property",)

    readonly_fields = ("created_at", "updated_at")

    inlines = [SubUnitInline, UnitImageInline]

    fieldsets = (
        ("Basic Info", {
            "fields": ("property", "unit_number", "unit_type")
        }),

        ("Details", {
            "fields": ("description", "rent", "capacity")
        }),

        ("Status", {
            "fields": ("is_active", "is_available_for_public")
        }),

        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    # 🔥 Occupancy दिखाने के लिए
    def is_occupied_status(self, obj):
        return obj.is_occupied()

    is_occupied_status.boolean = True
    is_occupied_status.short_description = "Occupied"


# 🔥 SubUnit Admin
class SubUnitAdmin(admin.ModelAdmin):

    list_display = (
        "subunit_number",
        "unit",
        "rent",
        "is_active",
        "is_occupied_status",
    )

    list_filter = ("is_active",)

    search_fields = (
        "subunit_number",
        "unit__unit_number",
    )

    autocomplete_fields = ("unit",)

    readonly_fields = ("created_at",)

    def is_occupied_status(self, obj):
        return obj.is_occupied()

    is_occupied_status.boolean = True
    is_occupied_status.short_description = "Occupied"


# 🔥 Unit Image Admin
class UnitImageAdmin(admin.ModelAdmin):

    list_display = ("unit", "is_primary", "created_at")

    list_filter = ("is_primary",)

    search_fields = ("unit__unit_number",)

    autocomplete_fields = ("unit",)

    readonly_fields = ("created_at",)


# 🔥 Register
admin.site.register(Unit, UnitAdmin)
admin.site.register(SubUnit, SubUnitAdmin)
admin.site.register(UnitImage, UnitImageAdmin)
