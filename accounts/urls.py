from django.urls import path
from .views import login_view, signup_view, logout_view
from .api import signup_api, login_api, logout_api

urlpatterns = [
    # path("", login_view),
    # path("login/", login_view),
    # path("signup/", signup_view),
    # path("logout/", logout_view),
    path("signup/", signup_api),
    path("login/", login_api),
    path("logout/", logout_api)
]