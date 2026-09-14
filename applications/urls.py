from django.urls import path

from .api import (
    applicant_create_api,
    applicant_detail_api,
    applicant_list_api,
    application_approve_api,
    application_create_api,
    application_detail_api,
    application_history_api,
    application_list_api,
    application_reject_api,
    application_review_api,
    application_submit_api,
    application_withdraw_api,
)

urlpatterns = [
    path("api/applicants/", applicant_list_api),
    path("api/applicants/create/", applicant_create_api),
    path("api/applicants/<int:applicant_id>/", applicant_detail_api),
    path("api/applications/", application_list_api),
    path("api/applications/create/", application_create_api),
    path("api/applications/<int:application_id>/", application_detail_api),
    path("api/applications/<int:application_id>/submit/", application_submit_api),
    path("api/applications/<int:application_id>/review/", application_review_api),
    path("api/applications/<int:application_id>/approve/", application_approve_api),
    path("api/applications/<int:application_id>/reject/", application_reject_api),
    path("api/applications/<int:application_id>/withdraw/", application_withdraw_api),
    path("api/applications/<int:application_id>/history/", application_history_api),
]
