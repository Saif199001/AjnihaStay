from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from .services import create_user_account, login_user_service
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserSerializer


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }

@api_view(["POST"])
def login_api(request):

    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password required"}, status=400)

    user = login_user_service(request, email, password)

    if user is not None:

        tokens = get_tokens_for_user(user)

        return Response({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
            },
            "tokens": tokens
        })

    return Response({"error": "Invalid credentials"}, status=401)

@api_view(["POST"])
def signup_api(request):

    try:
        email = request.data.get("email")
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        user = create_user_account(email, password, confirm_password)

        tokens = get_tokens_for_user(user)

        return Response({
            "message": "Account created",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
            },
            "tokens": tokens
        })

    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

@api_view(["POST"])
def logout_api(request):
    return Response({"message": "Logout success (client should delete token)"})