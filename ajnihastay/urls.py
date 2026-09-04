from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("workspaces.urls")),
    path("", include("properties.urls")),
    path("", include("unit.urls")),
    path("", include("tenant.urls")),
    path("", include("payments.urls")),
    path("", include("dashboard.urls")),
]
