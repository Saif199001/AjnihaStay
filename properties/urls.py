from django.urls import path
from .views import property_list_view, property_create_view
from .api import property_list_api, property_create_api

urlpatterns = [
    path("properties/", property_list_view),
    path("properties/add/", property_create_view),
    path("api/properties/", property_list_api),
    path("api/properties/create/", property_create_api),
]