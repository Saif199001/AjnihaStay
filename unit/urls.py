from django.urls import path
from .views import unit_list_view, unit_create_view, subunit_create_view
from .api import unit_list_api, unit_create_api, subunit_create_api


urlpatterns = [
    path("units/", unit_list_view),
    path("units/add/", unit_create_view),
    path("units/<int:unit_id>/subunits/add/", subunit_create_view),
    path("api/units/", unit_list_api),
    path("api/units/create/", unit_create_api),
    path("api/subunits/create/", subunit_create_api),
]
