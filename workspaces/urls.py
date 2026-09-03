from django.urls import path

from .api import workspace_list_api

urlpatterns = [
    path("api/workspaces/", workspace_list_api, name="workspace-list"),
]
