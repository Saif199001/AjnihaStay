from django.urls import path
from .api import tenant_list_api, tenant_create_api, occupancy_create_api, charge_create_api, charge_list_api

urlpatterns = [
    path("api/tenants/", tenant_list_api),
    path("api/tenants/create/", tenant_create_api),
    path("api/occupancy/create/", occupancy_create_api),
    path("api/charges/create/", charge_create_api),
    path("api/charges/", charge_list_api),
]