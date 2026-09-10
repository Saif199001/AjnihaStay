from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Prefetch, Q, Sum
from django.utils import timezone

from payments.models import Invoice
from tenant.models import Occupancy, Tenant
from unit.models import SubUnit, Unit


DEFAULT_AVAILABILITY_LIMIT = 100
DEFAULT_UPCOMING_VACANCY_LIMIT = 100
MAX_DASHBOARD_LIST_LIMIT = 500


def _current_occupancy_queryset(today):
    return Occupancy.objects.filter(
        is_active=True,
        check_in_date__lte=today,
    ).filter(Q(check_out_date__isnull=True) | Q(check_out_date__gte=today))


def _bounded_limit(value, default):
    if value is None:
        return default
    return min(value, MAX_DASHBOARD_LIST_LIMIT)


def _canonical_workspace_financial_rows(workspace):
    """Return invoice financial positions using the canonical Phase 3 equation.

    This is a read-model implementation of the same immutable financial components
    used by calculate_invoice_financial_position(). It deliberately does not read
    Invoice.paid_amount or Invoice.status.
    """
    invoices = list(
        Invoice.objects.filter(occupancy__tenant__workspace=workspace)
        .only("id", "total_amount", "due_date")
    )
    if not invoices:
        return []

    invoice_ids = [invoice.id for invoice in invoices]
    adjustments = {}
    for row in (
        workspace.financial_adjustments.filter(invoice_id__in=invoice_ids)
        .values("invoice_id", "adjustment_type")
        .annotate(total=Sum("amount"))
    ):
        adjustments.setdefault(row["invoice_id"], {})[row["adjustment_type"]] = row["total"] or Decimal("0")

    allocations = {
        row["invoice_id"]: row["total"] or Decimal("0")
        for row in workspace.payments.filter(invoice_id__in=invoice_ids)
        .values("invoice_id")
        .annotate(total=Sum("allocations__amount"))
    }

    advance_applications = {
        row["invoice_id"]: row["total"] or Decimal("0")
        for row in (
            __import__("payments.models", fromlist=["AdvanceCreditApplication"])
            .AdvanceCreditApplication.objects.filter(invoice_id__in=invoice_ids)
            .values("invoice_id")
            .annotate(total=Sum("amount"))
        )
    }

    reducing_types = {"credit", "discount", "waiver", "write_off"}
    rows = []
    for invoice in invoices:
        by_type = adjustments.get(invoice.id, {})
        debit = by_type.get("debit", Decimal("0"))
        reducing = sum(
            (by_type.get(kind, Decimal("0")) for kind in reducing_types),
            Decimal("0"),
        )
        gross = invoice.total_amount or Decimal("0")
        adjusted = gross + debit - reducing
        payment_settlement = allocations.get(invoice.id, Decimal("0"))
        advance_settlement = advance_applications.get(invoice.id, Decimal("0"))
        settlement = payment_settlement + advance_settlement
        outstanding = max(adjusted - settlement, Decimal("0"))
        rows.append(
            {
                "invoice_id": invoice.id,
                "gross_receivable": gross,
                "debit_adjustments": debit,
                "reducing_adjustments": reducing,
                "adjusted_receivable": adjusted,
                "settlement": settlement,
                "outstanding": outstanding,
                "due_date": invoice.due_date,
            }
        )
    return rows


def get_dashboard_data(
    workspace,
    *,
    period_start=None,
    period_end=None,
    upcoming_days=30,
    availability_limit=None,
    upcoming_vacancy_limit=None,
):
    """Build the read-only dashboard contract for one workspace."""
    today = timezone.localdate()
    period_start = period_start or today.replace(day=1)
    period_end = period_end or today
    availability_limit = _bounded_limit(availability_limit, DEFAULT_AVAILABILITY_LIMIT)
    upcoming_vacancy_limit = _bounded_limit(upcoming_vacancy_limit, DEFAULT_UPCOMING_VACANCY_LIMIT)

    current_occupancies = _current_occupancy_queryset(today)
    unit_occupancies = current_occupancies.filter(subunit_id__isnull=True)

    subunit_occupancy_qs = Prefetch(
        "occupancies",
        queryset=current_occupancies,
        to_attr="dashboard_current_occupancies",
    )
    active_subunits = (
        SubUnit.objects.filter(is_active=True)
        .prefetch_related(subunit_occupancy_qs)
        .order_by("subunit_number", "id")
    )
    active_units = (
        Unit.objects.filter(is_active=True, property__workspace=workspace, property__is_active=True)
        .prefetch_related(
            Prefetch("subunits", queryset=active_subunits, to_attr="dashboard_subunits"),
            Prefetch("occupancies", queryset=unit_occupancies, to_attr="dashboard_unit_occupancies"),
        )
        .select_related("property")
        .order_by("property_id", "unit_number", "id")
    )

    active_units = list(active_units)
    total_properties = workspace.workspace_properties.filter(is_active=True).count()
    total_units = len(active_units)
    total_unit_capacity = sum(unit.capacity for unit in active_units)
    occupied_unit_slots = sum(len(unit.dashboard_unit_occupancies) for unit in active_units)
    available_unit_slots = max(total_unit_capacity - occupied_unit_slots, 0)

    total_subunits = 0
    occupied_subunits = 0
    availability_total = 0
    available_spaces = []

    for unit in active_units:
        subunits = getattr(unit, "dashboard_subunits", [])
        total_subunits += len(subunits)
        for subunit in subunits:
            if getattr(subunit, "dashboard_current_occupancies", []):
                occupied_subunits += 1
            else:
                availability_total += 1
                if len(available_spaces) < availability_limit:
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
            availability_total += 1
            if len(available_spaces) < availability_limit:
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
    period_totals = period_invoices.aggregate(
        invoiced=Sum("total_amount"),
        rent=Sum("rent_amount"),
        charges=Sum("charges_amount"),
    )
    period_invoiced = period_totals["invoiced"] or Decimal("0")
    period_rent = period_totals["rent"] or Decimal("0")
    period_charges = period_totals["charges"] or Decimal("0")
    period_collected = (
        workspace.payments.filter(
            invoice__occupancy__tenant__workspace=workspace,
            payment_date__gte=period_start,
            payment_date__lte=period_end,
        )
        .aggregate(total=Sum("allocations__amount"))["total"]
        or Decimal("0")
    )

    financial_rows = _canonical_workspace_financial_rows(workspace)
    outstanding = sum((row["outstanding"] for row in financial_rows), Decimal("0"))
    overdue = sum(
        (
            row["outstanding"]
            for row in financial_rows
            if row["due_date"] < today and row["outstanding"] > 0
        ),
        Decimal("0"),
    )

    upcoming_end = today + timedelta(days=upcoming_days)
    upcoming_vacancies = []
    upcoming_vacancies_total = 0
    upcoming_queryset = (
        current_occupancies.filter(
            check_out_date__isnull=False,
            check_out_date__gte=today,
            check_out_date__lte=upcoming_end,
            tenant__workspace=workspace,
        )
        .select_related("tenant", "unit__property", "subunit")
        .order_by("check_out_date", "unit__property_id", "unit_id", "subunit_id", "id")
    )
    for occupancy in upcoming_queryset:
        upcoming_vacancies_total += 1
        if len(upcoming_vacancies) >= upcoming_vacancy_limit:
            continue
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
        "availability_total": availability_total,
        "availability_truncated": availability_total > len(available_spaces),
        "upcoming_vacancies": upcoming_vacancies,
        "upcoming_vacancies_total": upcoming_vacancies_total,
        "upcoming_vacancies_truncated": upcoming_vacancies_total > len(upcoming_vacancies),
    }
