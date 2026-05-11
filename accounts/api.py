from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from .services import create_user_account, login_user_service
from .serializers import UserSerializer


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