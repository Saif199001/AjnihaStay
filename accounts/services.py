from django.contrib.auth import authenticate
from .models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

def create_user_account(email, password, confirm_password):

    email = email.lower()

    if password != confirm_password:
        raise ValidationError("Passwords do not match")

    # 🔥 Django password validation
    validate_password(password)

    if User.objects.filter(email=email).exists():
        raise ValidationError("Email already exists")

    user = User.objects.create_user(
        email=email,
        password=password,
        role="owner"
    )

    return user


# 🔥 Login Service
def login_user_service(request, email, password):

    user = authenticate(request, email=email, password=password)

    return user