from django.contrib import admin
from .models import Tenant, Occupancy, Charge


class ChargeInline(admin.TabularInline):
    model = Charge
    extra = 1


class OccupancyInline(admin.TabularInline):
    model = Occupancy
    extra = 0
    readonly_fields = ("created_at",)


class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "state", "created_at")
    search_fields = ("full_name", "phone", "email")
    list_filter = ("state", "nationality")
    readonly_fields = ("created_at", "updated_at")
    inlines = [OccupancyInline]


class OccupancyAdmin(admin.ModelAdmin):
    list_display = ("tenant", "unit", "subunit", "rent", "billing_type", "billing_cycle", "check_in_date", "check_out_date", "is_active")
    list_filter = ("billing_type", "billing_cycle", "is_active")
    search_fields = ("tenant__full_name", "unit__unit_number")
    autocomplete_fields = ("tenant", "unit", "subunit", "allotted_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChargeInline]


class ChargeAdmin(admin.ModelAdmin):
    list_display = ("occupancy", "charge_type", "amount", "charge_date")
    list_filter = ("charge_type",)
    search_fields = ("occupancy__tenant__full_name",)
    autocomplete_fields = ("occupancy",)
    readonly_fields = ("created_at",)


# Intentionally not registered: forced RLS has no unrestricted Admin context.
