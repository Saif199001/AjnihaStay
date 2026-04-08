from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.http import HttpResponse
from .services import get_units, create_unit, create_subunit
from properties.models import Property
from .models import Unit


@login_required(login_url="/login/")
def unit_list_view(request):

    property_id = request.GET.get("property_id")

    units = get_units(request.user, property_id)
    units = units.prefetch_related("subunits", "images")

    properties = Property.objects.filter(owner=request.user)

    return render(request, "dashboard/units/list.html", {
        "units": units,
        "properties": properties
    })


@login_required(login_url="/login/")
def unit_create_view(request):

    properties = Property.objects.filter(owner=request.user)

    if request.method == "POST":
        create_unit(request.user, request.POST)
        return redirect("/units/")

    return render(request, "dashboard/units/create.html", {
        "properties": properties
    })


@login_required(login_url="/login/")
def subunit_create_view(request, unit_id):

    unit = Unit.objects.get(id=unit_id)

    if request.method == "POST":
        try:
            create_subunit({
                "unit": unit.id,
                "subunit_number": request.POST.get("subunit_number"),
                "rent": request.POST.get("rent")
            })

            # 🔥 HTMX response
            html = render_to_string(
                "dashboard/units/partials/subunit_list.html",
                {"u": unit}
            )
            return HttpResponse(html)

        except ValidationError as e:
            return HttpResponse(f"<div class='text-red-500 text-sm'>{str(e)}</div>")

    return render(request, "dashboard/units/subunit_create.html", {
        "unit": unit
    })