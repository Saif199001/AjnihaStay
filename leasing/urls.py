from django.urls import path

from .api import (
    lease_cancel_api,
    lease_create_api,
    lease_detail_api,
    lease_expire_api,
    lease_list_api,
    lease_notice_create_api,
    lease_notice_transition_api,
    lease_terminate_api,
    lease_transition_api,
    lease_update_api,
)

urlpatterns = [
    path("api/leases/", lease_list_api),
    path("api/leases/create/", lease_create_api),
    path("api/leases/<int:lease_id>/", lease_detail_api),
    path("api/leases/<int:lease_id>/update/", lease_update_api),
    path("api/leases/<int:lease_id>/transition/", lease_transition_api),
    path("api/leases/<int:lease_id>/expire/", lease_expire_api),
    path("api/leases/<int:lease_id>/terminate/", lease_terminate_api),
    path("api/leases/<int:lease_id>/cancel/", lease_cancel_api),
    path("api/leases/<int:lease_id>/notices/create/", lease_notice_create_api),
    path("api/leases/notices/<int:notice_id>/transition/", lease_notice_transition_api),
]
