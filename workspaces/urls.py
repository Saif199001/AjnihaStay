from django.urls import path

from .api import (
    workspace_current_api,
    workspace_list_api,
    workspace_member_deactivate_api,
    workspace_member_role_api,
    workspace_members_api,
)

urlpatterns = [
    path("api/workspaces/", workspace_list_api, name="workspace-list"),
    path("api/workspaces/current/", workspace_current_api, name="workspace-current"),
    path("api/workspaces/members/", workspace_members_api, name="workspace-members"),
    path("api/workspaces/members/<int:user_id>/role/", workspace_member_role_api, name="workspace-member-role"),
    path("api/workspaces/members/<int:user_id>/deactivate/", workspace_member_deactivate_api, name="workspace-member-deactivate"),
]
