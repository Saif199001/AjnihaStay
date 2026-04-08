from django.contrib import admin
from .models import Tenant, Occupancy, Charge


# 🔥 Charges Inline (Occupancy page पर charges दिखेंगे)
class ChargeInline(admin.TabularInline):
    model = Charge
    extra = 1


# 🔥 Occupancy Inline (Tenant page पर allotment दिखेगा)
class OccupancyInline(admin.TabularInline):
    model = Occupancy
    extra = 0
    readonly_fields = ("created_at",)


# 🔥 Tenant Admin
class TenantAdmin(admin.ModelAdmin):

    list_display = (
        "full_name",
        "phone",
        "email",
        "state",
        "created_at",
    )

    search_fields = (
        "full_name",
        "phone",
        "email",
    )

    list_filter = ("state", "nationality")

    readonly_fields = ("created_at", "updated_at")

    inlines = [OccupancyInline]

    fieldsets = (
        ("Basic Info", {
            "fields": ("full_name", "phone", "email", "profile_photo")
        }),

        ("Identity", {
            "fields": ("nationality", "id_proof_type", "id_number", "id_document")
        }),

        ("Address", {
            "fields": ("permanent_address", "district", "state", "pin_code")
        }),

        ("Emergency", {
            "fields": ("emergency_contact",)
        }),

        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


# 🔥 Occupancy Admin (MOST IMPORTANT 🔥)
class OccupancyAdmin(admin.ModelAdmin):

    list_display = (
        "tenant",
        "unit",
        "subunit",
        "rent",
        "billing_type",
        "billing_cycle",
        "check_in_date",
        "check_out_date",
        "is_active",
    )

    list_filter = (
        "billing_type",
        "billing_cycle",
        "is_active",
    )

    search_fields = (
        "tenant__full_name",
        "unit__unit_number",
    )

    autocomplete_fields = ("tenant", "unit", "subunit", "allotted_by")

    readonly_fields = ("created_at", "updated_at")

    inlines = [ChargeInline]

    fieldsets = (
        ("Tenant Info", {
            "fields": ("tenant",)
        }),

        ("Unit Info", {
            "fields": ("unit", "subunit")
        }),

        ("Billing", {
            "fields": ("rent", "billing_type", "billing_cycle")
        }),

        ("Dates", {
            "fields": ("check_in_date", "check_out_date", "next_due_date")
        }),

        ("Deposit", {
            "fields": ("security_deposit", "deposit_paid")
        }),

        ("Status", {
            "fields": ("is_active", "allotted_by")
        }),

        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


# 🔥 Charge Admin
class ChargeAdmin(admin.ModelAdmin):

    list_display = (
        "occupancy",
        "charge_type",
        "amount",
        "charge_date",
    )

    list_filter = ("charge_type",)

    search_fields = ("occupancy__tenant__full_name",)

    autocomplete_fields = ("occupancy",)

    readonly_fields = ("created_at",)


# 🔥 Register
admin.site.register(Tenant, TenantAdmin)
admin.site.register(Occupancy, OccupancyAdmin)
admin.site.register(Charge, ChargeAdmin)