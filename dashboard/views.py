from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .services import get_dashboard_data


@login_required(login_url="/login/")
def dashboard_view(request):

    data = get_dashboard_data(request.user)

    return render(request, "dashboard/dashboard.html", {"data": data})