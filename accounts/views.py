from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .services import create_user_account, login_user_service, send_email_verification


def signup_view(request):
    error = None
    verification_required = False

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        try:
            user = create_user_account(email, password, confirm_password)
            try:
                send_email_verification(user)
            except Exception:
                pass
            verification_required = True
        except ValidationError as exc:
            error = str(exc)

    return render(request, "auth/signup.html", {
        "error": error,
        "verification_required": verification_required,
    })


def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = login_user_service(request, email, password)

        if user and user.email_verified:
            login(request, user)
            return redirect("/dashboard/")

        if user and not user.email_verified:
            return render(
                request,
                "auth/login.html",
                {"error": "Email verification required"},
                status=403,
            )

        return render(request, "auth/login.html", {"error": "Invalid credentials"})

    return render(request, "auth/login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")
