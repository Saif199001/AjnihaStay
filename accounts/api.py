import os

import resend

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer
from .services import create_user_account, login_user_service

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@api_view(["POST"])
def login_api(request):
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password required"}, status=400)

    user = login_user_service(request, email, password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=401)

    if not user.is_active_account:
        return Response({"error": "Account is inactive"}, status=403)

    refresh = RefreshToken.for_user(user)

    return Response({
        "message": "Login successful",
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


@api_view(["POST"])
def signup_api(request):
    try:
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        if not email or not password or not confirm_password:
            return Response({"error": "All fields required"}, status=400)

        user = create_user_account(email, password, confirm_password)
        tokens = get_tokens_for_user(user)

        return Response({
            "message": "Account created",
            "user": UserSerializer(user).data,
            "tokens": tokens,
        }, status=201)

    except ValidationError as exc:
        return Response({"error": exc.messages}, status=400)


@api_view(["POST"])
def logout_api(request):
    refresh_token = request.data.get("refresh")

    if not refresh_token:
        return Response({"error": "Refresh token required"}, status=400)

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception:
        return Response({"error": "Invalid or expired token"}, status=400)

    return Response({"message": "Logout successful"})


@api_view(["POST"])
def forgot_password_api(request):
    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response({"error": "Email is required"}, status=400)

    # Do not reveal whether an email belongs to an account.
    generic_response = {"message": "If the account exists, a password reset link has been sent"}

    try:
        user = User.objects.get(email=email, is_active=True, is_active_account=True)
    except User.DoesNotExist:
        return Response(generic_response)

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"

    if not settings.RESEND_API_KEY:
        return Response({"error": "Password reset service is not configured"}, status=503)

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": os.getenv("EMAIL_FROM", "onboarding@resend.dev"),
            "to": email,
            "subject": "Reset your password",
            "html": (
                "<h2>Password Reset</h2>"
                "<p>Use the link below to reset your password.</p>"
                f'<a href="{reset_url}">Reset Password</a>'
            ),
        })
    except Exception:
        return Response({"error": "Unable to send password reset email"}, status=503)

    return Response(generic_response)


@api_view(["POST"])
def reset_password_api(request, uidb64, token):
    password = request.data.get("password")
    confirm_password = request.data.get("confirm_password")

    if not password or not confirm_password:
        return Response({"error": "Password and confirmation are required"}, status=400)

    if password != confirm_password:
        return Response({"error": "Passwords do not match"}, status=400)

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid, is_active=True, is_active_account=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"error": "Invalid link"}, status=400)

    if not default_token_generator.check_token(user, token):
        return Response({"error": "Invalid or expired token"}, status=400)

    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(password, user=user)
    except ValidationError as exc:
        return Response({"error": exc.messages}, status=400)

    user.set_password(password)
    user.save(update_fields=["password"])

    # Revoke all outstanding refresh tokens after a password reset.
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
    except Exception:
        # Do not expose token-revocation implementation details to the client.
        pass

    return Response({"message": "Password reset successful"})
