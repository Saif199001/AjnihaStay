from unit.models import Unit
from tenant.models import Occupancy
from payments.models import Payment
from django.db.models import Sum


def get_dashboard_data(user):

    total_units = Unit.objects.filter(
        property__owner=user
    ).count()

    occupied = Occupancy.objects.filter(
        unit__property__owner=user,
        is_active=True
    ).count()

    vacant = total_units - occupied

    revenue = Payment.objects.filter(
        invoice__occupancy__unit__property__owner=user
    ).aggregate(total=Sum("amount"))["total"] or 0

    return {
        "total_units": total_units,
        "occupied": occupied,
        "vacant": vacant,
        "revenue": revenue
    }