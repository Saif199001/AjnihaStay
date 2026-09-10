from django.urls import path

from .adjustment_api import financial_adjustment_create_api
from .api import (
    advance_credit_apply_api,
    advance_credit_collection_api,
    advance_credit_detail_api,
    billing_schedule_create_api,
    billing_schedule_detail_api,
    billing_schedule_list_api,
    billing_schedule_update_api,
    invoice_create_api,
    invoice_list_api,
    invoice_detail_api,
    payment_create_api,
    payment_allocation_create_api,
    payment_list_api,
    final_settlement_api,
    generate_invoice_api,
)
from .final_settlement_api import final_settlement_finalize_api
from .refund_api import payment_refund_create_api, payment_refund_transition_api

urlpatterns = [
    path("api/invoices/create/", invoice_create_api),
    path("api/invoices/", invoice_list_api),
    path("api/invoices/<int:invoice_id>/", invoice_detail_api),

    path("api/payments/create/", payment_create_api),
    path("api/payments/<int:payment_id>/allocations/", payment_allocation_create_api),
    path("api/payments/<int:payment_id>/refunds/", payment_refund_create_api),
    path("api/payments/", payment_list_api),
    path("api/payment-refunds/<int:refund_id>/", payment_refund_transition_api),
    path("api/final-settlement/<int:occupancy_id>/", final_settlement_api),
    path("api/final-settlement/<int:occupancy_id>/settle/", final_settlement_finalize_api),
    path("api/generate-invoices/", generate_invoice_api),

    path("api/billing-schedules/", billing_schedule_list_api),
    path("api/billing-schedules/create/", billing_schedule_create_api),
    path("api/billing-schedules/<int:schedule_id>/", billing_schedule_detail_api),
    path("api/billing-schedules/<int:schedule_id>/update/", billing_schedule_update_api),

    path("api/advance-credits/", advance_credit_collection_api),
    path("api/advance-credits/<int:credit_id>/", advance_credit_detail_api),
    path("api/advance-credits/<int:credit_id>/apply/", advance_credit_apply_api),

    path("api/financial-adjustments/create/", financial_adjustment_create_api),
]
