# Recurring Billing Worker Contract

Status: **deployment preparation only**

The application now exposes a durable, idempotent recurring-billing service boundary without coupling financial truth to a specific scheduler.

## Runtime contract

A future worker must call:

- `payments.recurring_billing_service.generate_due_recurring_billing(user, workspace, schedule, as_of_date, catch_up=True, max_occurrences=12)`

The worker must not write `Charge`, `Invoice`, `BillingSchedule`, or ledger rows directly.

## Required deployment properties

1. Run at most once per schedule at a time; database row locking remains authoritative.
2. Use a durable scheduler/queue with retry support.
3. Retry the same occurrence safely; charge identity is `(billing_schedule, charge_date)` and invoice identity is `(occupancy, billing_start, billing_end)`.
4. Preserve the bounded catch-up limit; a backlog must be drained across multiple worker runs rather than in one unbounded transaction.
5. Emit operational logs/metrics for attempted, generated, idempotent-replay, failed, and terminal schedules.
6. Do not put financial state transitions into cron glue or task callbacks.
7. Worker retries must preserve the service transaction boundary: a failed charge/invoice occurrence leaves the schedule cursor unchanged.

## Catch-up policy

Catch-up is explicit and bounded. The service processes due occurrences in chronological order, up to `max_occurrences` (default 12, hard maximum 100). If more backlog remains, the next worker run continues from the durable `next_run_date` cursor.

## Checkout policy

`check_out_date` is a terminal boundary. No new recurring occurrence is generated on or after checkout. The schedule is deactivated once its next run reaches checkout.

## Monthly policy

Monthly schedules persist an `anchor_day` from 1–31. If a month has fewer days, the occurrence uses that month's final day, while the stored anchor remains unchanged. This prevents Jan-31 → Feb-28 → Mar-28 drift.
