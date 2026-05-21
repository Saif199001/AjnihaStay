import resend
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from .services import create_user_account, login_user_service
from .serializers import UserSerializer
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }

@api_view(["POST"])
def login_api(request):

    email = request.data.get("email", "").lower()
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password required"}, status=400)

    user = login_user_service(request, email, password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=401)

    # 🔥 NEW CHECK
    if not user.is_active_account:
        return Response({"error": "Account is inactive"}, status=403)

    refresh = RefreshToken.for_user(user)

    return Response({
        "message": "Login successful",
        "access": str(refresh.access_token),
        "refresh": str(refresh)
    })

@api_view(["POST"])
def signup_api(request):

    try:
        email = request.data.get("email")
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
        })

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["POST"])
def logout_api(request):

    try:
        refresh_token = request.data.get("refresh")

        token = RefreshToken(refresh_token)
        token.blacklist()

        return Response({"message": "Logout successful"})

    except Exception as e:
        return Response({"error": "Invalid token"}, status=400)

@api_view(["POST"])
def forgot_password_api(request):

    print("EMAIL USER:", settings.EMAIL_HOST_USER)
    print("EMAIL PASS:", settings.EMAIL_HOST_PASSWORD)

    email = request.data.get("email")

    try:
        user = User.objects.get(email=email)

    except User.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=404
        )

    uid = urlsafe_base64_encode(force_bytes(user.pk))

    token = default_token_generator.make_token(user)

    reset_url = (
        f"http://localhost:3000/reset-password/"
        f"{uid}/{token}/"
    )

    resend.api_key = settings.RESEND_API_KEY

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": email,
        "subject": "Reset your password",
        "html": f"""
            <h2>Password Reset</h2>

            <p>Click below:</p>

            <a href="{reset_url}">
                Reset Password
            </a>
        """
    })

    return Response({
        "message": "Password reset link sent"
    })

@api_view(["POST"])
def reset_password_api(request, uidb64, token):

    password = request.data.get("password")
    confirm_password = request.data.get("confirm_password")

    if password != confirm_password:
        return Response(
            {"error": "Passwords do not match"},
            status=400
        )

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))

        user = User.objects.get(pk=uid)

    except Exception:
        return Response(
            {"error": "Invalid link"},
            status=400
        )

    if not default_token_generator.check_token(user, token):

        return Response(
            {"error": "Invalid or expired token"},
            status=400
        )

    user.set_password(password)
    user.save()

    return Response({
        "message": "Password reset successful"
    })