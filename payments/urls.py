from django.urls import path
from .api import (
    invoice_create_api,
    invoice_list_api,
    invoice_detail_api,
    payment_create_api,
    payment_list_api,
    final_settlement_api,
    generate_invoice_api
)

urlpatterns = [
    path("api/invoices/create/", invoice_create_api),
    path("api/invoices/", invoice_list_api),
    path("api/invoices/<int:invoice_id>/", invoice_detail_api),

    path("api/payments/create/", payment_create_api),
    path("api/payments/", payment_list_api),
    path(
    "api/final-settlement/<int:occupancy_id>/",
    final_settlement_api),
    path(
    "api/generate-invoices/",
    generate_invoice_api),
]