from django.urls import path

from .views import DashboardAPIView, dashboard_view

urlpatterns = [
    path("dashboard/", dashboard_view),
    path("api/dashboard/", DashboardAPIView.as_view()),
]
