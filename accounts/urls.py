from django.urls import path

from .api import (
    forgot_password_api,
    login_api,
    logout_api,
    resend_verification_api,
    reset_password_api,
    signup_api,
    verify_email_api,
)

urlpatterns = [
    # Canonical API contract.
    path("api/signup/", signup_api),
    path("api/login/", login_api),
    path("api/logout/", logout_api),
    path("api/forgot-password/", forgot_password_api),
    path("api/reset-password/<uidb64>/<token>/", reset_password_api),
    path("api/verify-email/<uidb64>/<token>/", verify_email_api),
    path("api/resend-verification/", resend_verification_api),

    # Backward-compatible aliases retained until consumers are migrated.
    path("signup/", signup_api),
    path("login/", login_api),
    path("logout/", logout_api),
    path("forgot-password/", forgot_password_api),
    path("reset-password/<uidb64>/<token>/", reset_password_api),
    path("verify-email/<uidb64>/<token>/", verify_email_api),
    path("resend-verification/", resend_verification_api),
]
