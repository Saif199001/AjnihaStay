from datetime import date, timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.utils import timezone

from payments.models import Invoice, Payment
from tenant.models import Occupancy, Tenant
from unit.models import SubUnit, Unit


def _current_occupancy_queryset(today):
    return Occupancy.objects.filter(
        is_active=True,
        check_in_date__lte=today,
    ).filter(Q(check_out_date__isnull=True) | Q(check_out_date__gte=today))


def get_dashboard_data(workspace, *, period_start=None, period_end=None, upcoming_days=30):
    """Build the read-only dashboard contract for one workspace."""
    today = timezone.localdate()
    period_start = period_start or today.replace(day=1)
    period_end = period_end or today

    current_occupancies = _current_occupancy_queryset(today)
    unit_occupancies = current_occupancies.filter(subunit_id__isnull=True)

    subunit_occupancy_qs = Prefetch(
        "occupancies",
        queryset=current_occupancies,
        to_attr="dashboard_current_occupancies",
    )
    active_subunits = SubUnit.objects.filter(is_active=True).prefetch_related(subunit_occupancy_qs)
    active_units = (
        Unit.objects.filter(is_active=True, property__workspace=workspace, property__is_active=True)
        .prefetch_related(
            Prefetch("subunits", queryset=active_subunits, to_attr="dashboard_subunits"),
            Prefetch("occupancies", queryset=unit_occupancies, to_attr="dashboard_unit_occupancies"),
        )
        .select_related("property")
        .order_by("property_id", "unit_number")
    )

    active_units = list(active_units)
    total_properties = workspace.workspace_properties.filter(is_active=True).count()
    total_units = len(active_units)
    total_unit_capacity = sum(unit.capacity for unit in active_units)
    occupied_unit_slots = sum(len(unit.dashboard_unit_occupancies) for unit in active_units)
    available_unit_slots = max(total_unit_capacity - occupied_unit_slots, 0)

    total_subunits = 0
    occupied_subunits = 0
    available_spaces = []

    for unit in active_units:
        subunits = getattr(unit, "dashboard_subunits", [])
        total_subunits += len(subunits)
        for subunit in subunits:
            if getattr(subunit, "dashboard_current_occupancies", []):
                occupied_subunits += 1
            else:
                available_spaces.append(
                    {
                        "property_id": unit.property_id,
                        "property_name": unit.property.name,
                        "unit_id": unit.id,
                        "unit_number": unit.unit_number,
                        "subunit_id": subunit.id,
                        "subunit_number": subunit.subunit_number,
                        "available_capacity": 1,
                        "type": "subunit",
                    }
                )

        unit_remaining = max(unit.capacity - len(unit.dashboard_unit_occupancies), 0)
        if unit_remaining:
            available_spaces.append(
                {
                    "property_id": unit.property_id,
                    "property_name": unit.property.name,
                    "unit_id": unit.id,
                    "unit_number": unit.unit_number,
                    "subunit_id": None,
                    "subunit_number": None,
                    "available_capacity": unit_remaining,
                    "type": "unit",
                }
            )

    available_subunits = total_subunits - occupied_subunits
    active_tenants = (
        Tenant.objects.filter(workspace=workspace, occupancies__in=current_occupancies)
        .distinct()
        .count()
    )

    period_invoices = Invoice.objects.filter(
        occupancy__tenant__workspace=workspace,
        billing_start__lte=period_end,
        billing_end__gte=period_start,
    )
    period_invoiced = period_invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    period_rent = period_invoices.aggregate(total=Sum("rent_amount"))["total"] or Decimal("0")
    period_charges = period_invoices.aggregate(total=Sum("charges_amount"))["total"] or Decimal("0")
    period_collected = (
        Payment.objects.filter(
            invoice__occupancy__tenant__workspace=workspace,
            payment_date__gte=period_start,
            payment_date__lte=period_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    outstanding_expression = ExpressionWrapper(
        F("total_amount") - F("paid_amount"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    outstanding = Invoice.objects.filter(occupancy__tenant__workspace=workspace).aggregate(
        total=Sum(outstanding_expression)
    )["total"] or Decimal("0")
    overdue = (
        Invoice.objects.filter(occupancy__tenant__workspace=workspace, due_date__lt=today)
        .exclude(status="paid")
        .aggregate(total=Sum(outstanding_expression))["total"]
        or Decimal("0")
    )

    upcoming_end = today + timedelta(days=upcoming_days)
    upcoming_vacancies = []
    for occupancy in current_occupancies.filter(
        check_out_date__isnull=False,
        check_out_date__gte=today,
        check_out_date__lte=upcoming_end,
        tenant__workspace=workspace,
    ).select_related("tenant", "unit__property", "subunit"):
        upcoming_vacancies.append(
            {
                "occupancy_id": occupancy.id,
                "property_id": occupancy.unit.property_id,
                "property_name": occupancy.unit.property.name,
                "unit_id": occupancy.unit_id,
                "unit_number": occupancy.unit.unit_number,
                "subunit_id": occupancy.subunit_id,
                "subunit_number": occupancy.subunit.subunit_number if occupancy.subunit_id else None,
                "tenant_id": occupancy.tenant_id,
                "tenant_name": occupancy.tenant.full_name,
                "vacancy_date": occupancy.check_out_date,
            }
        )

    occupancy_rate = (occupied_unit_slots / total_unit_capacity * 100) if total_unit_capacity else 0
    collection_rate = (period_collected / period_invoiced * 100) if period_invoiced else 0

    return {
        "as_of": today,
        "period": {"start": period_start, "end": period_end},
        "summary": {
            "total_properties": total_properties,
            "total_units": total_units,
            "total_unit_capacity": total_unit_capacity,
            "occupied_unit_slots": occupied_unit_slots,
            "available_unit_slots": available_unit_slots,
            "occupancy_rate": round(occupancy_rate, 2),
            "active_tenants": active_tenants,
            "total_subunits": total_subunits,
            "occupied_subunits": occupied_subunits,
            "available_subunits": available_subunits,
        },
        "financial": {
            "period_invoiced": period_invoiced,
            "period_rent": period_rent,
            "period_charges": period_charges,
            "period_collected": period_collected,
            "collection_rate": round(collection_rate, 2),
            "outstanding": outstanding,
            "overdue": overdue,
        },
        "availability": available_spaces,
        "upcoming_vacancies": upcoming_vacancies,
    }
