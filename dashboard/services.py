from django.db.models import Sum

from payments.models import Payment
from tenant.models import Occupancy
from unit.models import Unit


def get_dashboard_data(workspace):
    total_units = Unit.objects.filter(
        property__workspace=workspace,
        is_active=True,
    ).count()

    occupied = Occupancy.objects.filter(
        unit__property__workspace=workspace,
        is_active=True,
    ).count()

    vacant = total_units - occupied

    revenue = Payment.objects.filter(
        invoice__occupancy__unit__property__workspace=workspace,
    ).aggregate(total=Sum("amount"))["total"] or 0

    return {
        "total_units": total_units,
        "occupied": occupied,
        "vacant": vacant,
        "revenue": revenue,
    }
