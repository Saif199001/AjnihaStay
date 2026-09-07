import uuid
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.timezone import now

from tenant.models import Occupancy
from workspaces.db import set_workspace_context
from workspaces.models import Workspace


def generate_invoice_number():
    return "INV-" + uuid.uuid4().hex[:8].upper()


def generate_recurring_invoices():
    """Generate due recurring invoices through the canonical invoice service.

    This is intended for a trusted scheduled/background job, not a normal
    tenant-facing endpoint. Workspace context and recurring cursor movement
    remain orchestration concerns; invoice creation is delegated to the
    canonical domain service.
    """
    from .invoice_generation_service import generate_invoice_for_occupancy

    today = now().date()
    created_count = 0

    for workspace_id in Workspace.objects.filter(is_active=True).values_list("id", flat=True):
        workspace = Workspace.objects.get(id=workspace_id)
        with transaction.atomic():
            set_workspace_context(workspace_id)

            due_occupancy_ids = list(
                Occupancy.objects.filter(
                    is_active=True,
                    next_due_date__lte=today,
                ).values_list("id", flat=True)
            )

            for occupancy_id in due_occupancy_ids:
                try:
                    occupancy = Occupancy.objects.select_for_update().get(
                        id=occupancy_id,
                        is_active=True,
                    )
                except Occupancy.DoesNotExist:
                    continue

                if occupancy.next_due_date > today:
                    continue

                billing_start = occupancy.next_due_date
                if occupancy.billing_cycle == "monthly":
                    billing_end = billing_start + relativedelta(months=1)
                else:
                    billing_end = billing_start + timedelta(days=1)

                invoice, created = generate_invoice_for_occupancy(
                    None,
                    workspace,
                    occupancy,
                    billing_start,
                    billing_end,
                    billing_start,
                )

                if not created:
                    continue

                occupancy.next_due_date = billing_end
                occupancy.save()
                created_count += 1

    return created_count
