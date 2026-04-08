from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .services import create_user_account, login_user_service
from django.core.exceptions import ValidationError

def signup_view(request):

    error = None

    if request.method == "POST":

        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        try:
            user = create_user_account(email, password, confirm_password)
            login(request, user)
            return redirect("/dashboard/")
        except ValidationError as e:
            error = str(e)

    return render(request, "auth/signup.html", {
        "error": error
    })


# 🔥 LOGIN VIEW
def login_view(request):

    if request.method == "POST":

        email = request.POST.get("email")
        password = request.POST.get("password")

        user = login_user_service(request, email, password)

        if user:
            login(request, user)
            return redirect("/dashboard/")
        else:
            return render(request, "auth/login.html", {"error": "Invalid credentials"})

    return render(request, "auth/login.html")


# 🔥 LOGOUT
def logout_view(request):
    logout(request)
    return redirect("/login/")
