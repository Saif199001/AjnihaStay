import uuid
from django.utils.timezone import now
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from tenant.models import Occupancy


def generate_invoice_number():
    return "INV-" + uuid.uuid4().hex[:8].upper()

def generate_recurring_invoices():

    from .models import Invoice

    occupancies = Occupancy.objects.filter(
        is_active=True,
        next_due_date__lte=today
    )

    for occupancy in occupancies:

        # 🔥 SKIP if invoice already exists
        existing_invoice = Invoice.objects.filter(
            occupancy=occupancy,
            due_date=occupancy.next_due_date
        ).exists()

        if existing_invoice:
            continue

        billing_start = occupancy.next_due_date

        # 🔥 MONTHLY BILLING
        if occupancy.billing_cycle == "monthly":

            billing_end = (
                billing_start +
                relativedelta(months=1)
            )

        # 🔥 DAILY BILLING
        else:

            billing_end = (
                billing_start +
                timedelta(days=1)
            )

        Invoice.objects.create(

            occupancy=occupancy,

            billing_start=billing_start,

            billing_end=billing_end,

            rent_amount=occupancy.rent,

            charges_amount=0,

            due_date=billing_start,
        )

        # 🔥 UPDATE NEXT DUE DATE
        occupancy.next_due_date = billing_end

        occupancy.save()