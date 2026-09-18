import os

import resend

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer
from .services import (
    create_user_account,
    login_user_service,
    send_email_verification,
    verify_user_email,
)

User = get_user_model()


def get_tokens_for_user(user):
    if not user.is_active:
        raise ValidationError("Account is inactive")
    if not user.email_verified:
        raise ValidationError("Email verification required")

    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password required"}, status=400)

    user = login_user_service(request, email, password)
    if user is None:
        return Response({"error": "Invalid credentials"}, status=401)

    try:
        tokens = get_tokens_for_user(user)
    except ValidationError as exc:
        return Response({"error": exc.messages[0] if exc.messages else "Authentication rejected"}, status=403)

    return Response({"message": "Login successful", **tokens})


@api_view(["POST"])
@permission_classes([AllowAny])
def signup_api(request):
    try:
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")
        workspace_name = request.data.get("workspace_name")

        if not email or not password or not confirm_password:
            return Response({"error": "All fields required"}, status=400)

        try:
            user = create_user_account(email, password, confirm_password, workspace_name)
        except IntegrityError:
            return Response({"error": ["Email already exists"]}, status=400)

        verification_email_sent = False
        try:
            send_email_verification(user)
            verification_email_sent = True
        except Exception:
            # The account remains safely unverified; the resend endpoint can recover
            # from temporary email-provider/configuration failures.
            verification_email_sent = False

        return Response({
            "message": "Account created",
            "user": UserSerializer(user).data,
            "email_verification_required": True,
            "verification_email_sent": verification_email_sent,
        }, status=201)

    except ValidationError as exc:
        return Response({"error": exc.messages}, status=400)


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email_api(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"error": "Invalid verification link"}, status=400)

    if user.email_verified:
        return Response({"message": "Email already verified"})

    try:
        verify_user_email(user, token)
    except ValidationError as exc:
        return Response({"error": exc.messages}, status=400)

    return Response({"message": "Email verified successfully"})


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_verification_api(request):
    email = request.data.get("email", "").strip().lower()
    if not email:
        return Response({"error": "Email is required"}, status=400)

    generic_response = {
        "message": "If the account exists and is not verified, a verification email has been sent"
    }

    try:
        user = User.objects.get(email=email, is_active=True, email_verified=False)
    except User.DoesNotExist:
        return Response(generic_response)

    try:
        send_email_verification(user)
    except Exception:
        return Response(generic_response)

    return Response(generic_response)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_api(request):
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"error": "Refresh token required"}, status=400)

    try:
        RefreshToken(refresh_token).blacklist()
    except Exception:
        return Response({"error": "Invalid or expired token"}, status=400)

    return Response({"message": "Logout successful"})


@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password_api(request):
    email = request.data.get("email", "").strip().lower()
    if not email:
        return Response({"error": "Email is required"}, status=400)

    generic_response = {"message": "If the account exists, a password reset link has been sent"}

    try:
        user = User.objects.get(email=email, is_active=True)
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
@permission_classes([AllowAny])
def reset_password_api(request, uidb64, token):
    password = request.data.get("password")
    confirm_password = request.data.get("confirm_password")
    if not password or not confirm_password:
        return Response({"error": "Password and confirmation are required"}, status=400)
    if password != confirm_password:
        return Response({"error": "Passwords do not match"}, status=400)

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"error": "Invalid link"}, status=400)

    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk, is_active=True)

            if not default_token_generator.check_token(user, token):
                return Response({"error": "Invalid or expired token"}, status=400)

            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                return Response({"error": exc.messages}, status=400)

            user.set_password(password)
            user.save(update_fields=["password"])

            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
    except Exception:
        return Response({"error": "Unable to complete password reset"}, status=503)

    return Response({"message": "Password reset successful"})
