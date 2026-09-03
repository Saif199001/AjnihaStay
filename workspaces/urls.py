from django.urls import path

from .api import workspace_current_api, workspace_list_api

urlpatterns = [
    path("api/workspaces/", workspace_list_api, name="workspace-list"),
    path("api/workspaces/current/", workspace_current_api, name="workspace-current"),
]
