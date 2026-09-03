from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.template.loader import render_to_string

from properties.models import Property
from workspaces.context import get_workspace_for_request
from workspaces.db import set_workspace_context
from workspaces.permissions import ROLE_RANK
from .services import get_units, create_unit, create_subunit
from .models import Unit


def _workspace_for_view(request, minimum_role="staff"):
    try:
        workspace, membership = get_workspace_for_request(request)
        if ROLE_RANK[membership.role] < ROLE_RANK[minimum_role]:
            return None, HttpResponseForbidden("Insufficient workspace role")
        set_workspace_context(workspace.id)
        return workspace, None
    except Exception as exc:
        return None, HttpResponseForbidden(str(exc))


@login_required(login_url="/login/")
def unit_list_view(request):
    workspace, error = _workspace_for_view(request, "staff")
    if error:
        return error

    property_id = request.GET.get("property_id")
    units = get_units(workspace, property_id).prefetch_related("subunits", "images")
    properties = Property.objects.filter(workspace=workspace, is_active=True).order_by("id")

    return render(request, "dashboard/units/list.html", {
        "units": units,
        "properties": properties,
    })


@login_required(login_url="/login/")
def unit_create_view(request):
    workspace, error = _workspace_for_view(request, "manager")
    if error:
        return error

    properties = Property.objects.filter(workspace=workspace, is_active=True).order_by("id")

    if request.method == "POST":
        try:
            create_unit(workspace, request.POST)
        except ValidationError as exc:
            return HttpResponse(str(exc), status=400)
        return redirect("/units/")

    return render(request, "dashboard/units/create.html", {
        "properties": properties,
    })


@login_required(login_url="/login/")
def subunit_create_view(request, unit_id):
    workspace, error = _workspace_for_view(request, "manager")
    if error:
        return error

    try:
        unit = Unit.objects.get(id=unit_id, property__workspace=workspace)
    except Unit.DoesNotExist:
        return HttpResponseForbidden("Unit not found")

    if request.method == "POST":
        try:
            create_subunit(workspace, {
                "unit": unit.id,
                "subunit_number": request.POST.get("subunit_number"),
                "rent": request.POST.get("rent"),
            })

            html = render_to_string(
                "dashboard/units/partials/subunit_list.html",
                {"u": unit},
            )
            return HttpResponse(html)

        except ValidationError as exc:
            return HttpResponse(f"<div class='text-red-500 text-sm'>{str(exc)}</div>", status=400)

    return render(request, "dashboard/units/subunit_create.html", {
        "unit": unit,
    })
