from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .services import get_properties, create_property


# 🔥 LIST VIEW
@login_required(login_url="/login/")
def property_list_view(request):

    properties = get_properties(request.user)

    return render(request, "dashboard/properties/list.html", {
        "properties": properties
    })


# 🔥 CREATE VIEW
@login_required(login_url="/login/")
def property_create_view(request):

    if request.method == "POST":

        create_property(request.user, request.POST, request.FILES)

        return redirect("/properties/")

    return render(request, "dashboard/properties/create.html")
