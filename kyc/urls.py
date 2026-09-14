from django.urls import path

from .api import (
    kyc_agreements_api,
    kyc_detail_api,
    kyc_document_download_api,
    kyc_document_history_api,
    kyc_document_review_api,
    kyc_documents_api,
    kyc_history_api,
    kyc_reject_api,
    kyc_submit_api,
    kyc_verify_api,
)

urlpatterns = [
    path("api/tenants/<int:tenant_id>/kyc/", kyc_detail_api),
    path("api/tenants/<int:tenant_id>/kyc/submit/", kyc_submit_api),
    path("api/tenants/<int:tenant_id>/kyc/verify/", kyc_verify_api),
    path("api/tenants/<int:tenant_id>/kyc/reject/", kyc_reject_api),
    path("api/tenants/<int:tenant_id>/kyc/history/", kyc_history_api),
    path("api/tenants/<int:tenant_id>/kyc/documents/", kyc_documents_api),
    path("api/kyc/documents/<int:document_id>/review/", kyc_document_review_api),
    path("api/kyc/documents/<int:document_id>/download/", kyc_document_download_api),
    path("api/kyc/documents/<int:document_id>/history/", kyc_document_history_api),
    path("api/tenants/<int:tenant_id>/agreements/", kyc_agreements_api),
]
