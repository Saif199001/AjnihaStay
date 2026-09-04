from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView

from workspaces.permissions import WorkspaceStaffPermission
from workspaces.context import get_workspace_for_request
from workspaces.db import set_workspace_context
from .services import get_dashboard_data


class DashboardAPIView(APIView):
    permission_classes = [WorkspaceStaffPermission]

    def get(self, request):
        return Response(get_dashboard_data(request.workspace))


@login_required(login_url="/login/")
def dashboard_view(request):
    try:
        workspace, _ = get_workspace_for_request(request)
        set_workspace_context(workspace.id)
    except Exception:
        return HttpResponseForbidden("Workspace access denied")

    data = get_dashboard_data(workspace)
    return render(request, "dashboard/dashboard.html", {"data": data})
