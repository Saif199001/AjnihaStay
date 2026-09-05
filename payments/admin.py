from django.contrib import admin
from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ("created_at",)


class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "occupancy", "billing_start", "billing_end", "total_amount", "paid_amount", "status", "due_date", "created_at")
    list_filter = ("status", "due_date")
    search_fields = ("invoice_number", "occupancy__tenant__full_name")
    autocomplete_fields = ("occupancy",)
    readonly_fields = ("invoice_number", "created_at")
    inlines = [PaymentInline]


class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "payment_method", "payment_date", "reference_id", "created_at")
    list_filter = ("payment_method", "payment_date")
    search_fields = ("invoice__invoice_number",)
    autocomplete_fields = ("invoice",)
    readonly_fields = ("created_at",)


# Intentionally not registered: forced RLS has no unrestricted Admin context.
