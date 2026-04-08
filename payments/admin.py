from django.contrib import admin
from .models import Invoice, Payment


# 🔥 Payment Inline (Invoice page पर payments दिखेंगे)
class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ("created_at",)


# 🔥 Invoice Admin (🔥 MOST IMPORTANT)
class InvoiceAdmin(admin.ModelAdmin):

    list_display = (
        "invoice_number",
        "occupancy",
        "billing_start",
        "billing_end",
        "total_amount",
        "paid_amount",
        "status",
        "due_date",
        "created_at",
    )

    list_filter = (
        "status",
        "due_date",
    )

    search_fields = (
        "invoice_number",
        "occupancy__tenant__full_name",
    )

    autocomplete_fields = ("occupancy",)

    readonly_fields = ("invoice_number", "created_at")

    inlines = [PaymentInline]

    fieldsets = (
        ("Invoice Info", {
            "fields": ("invoice_number", "occupancy")
        }),

        ("Billing Period", {
            "fields": ("billing_start", "billing_end")
        }),

        ("Amounts", {
            "fields": ("rent_amount", "charges_amount", "total_amount")
        }),

        ("Payment Status", {
            "fields": ("paid_amount", "status")
        }),

        ("Due Info", {
            "fields": ("due_date",)
        }),

        ("Timestamp", {
            "fields": ("created_at",)
        }),
    )


# 🔥 Payment Admin
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        "invoice",
        "amount",
        "payment_method",
        "payment_date",
        "reference_id",
        "created_at",
    )

    list_filter = (
        "payment_method",
        "payment_date",
    )

    search_fields = (
        "invoice__invoice_number",
    )

    autocomplete_fields = ("invoice",)

    readonly_fields = ("created_at",)

    fieldsets = (
        ("Payment Info", {
            "fields": ("invoice", "amount", "payment_method")
        }),

        ("Details", {
            "fields": ("payment_date", "reference_id", "notes")
        }),

        ("Timestamp", {
            "fields": ("created_at",)
        }),
    )


# 🔥 Register
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(Payment, PaymentAdmin)