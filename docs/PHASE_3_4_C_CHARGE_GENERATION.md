# AjnihaStay — Phase 3.4-C Charge Generation Foundation

**Status:** LOCKED
**Phase:** 3.4 Recurring Billing Foundation

## Objective

Create the canonical domain-service seam that turns an active `BillingSchedule` into one `tenant.Charge` without generating invoices, mutating payments, or advancing the schedule cursor.

## In Scope

- Workspace-scoped schedule lookup.
- Active schedule validation.
- Active occupancy validation.
- Explicit charge date supplied by the caller.
- Charge creation using the existing `tenant.Charge` model.
- Schedule amount as the generated charge amount.
- `custom` charge type for recurring-generated charges until a dedicated charge-source taxonomy is explicitly designed.
- Deterministic description identifying the recurring schedule.
- Transactional creation.
- Focused tests for happy path, inactive schedule/occupancy, workspace isolation, invalid dates, and no invoice/payment side effects.

## Out of Scope

- Invoice generation.
- Payment creation or allocation.
- Advancing `next_run_date`.
- Daily/monthly date calculation.
- Scheduler/cron/Celery execution.
- Retry/idempotency ledger or event table.
- New `Charge` schema fields or database migrations.
- Automatic charge generation from API requests.

## Financial Invariants

1. A generated charge belongs to the same workspace as the schedule's occupancy.
2. Charge amount equals the schedule amount at generation time.
3. The service does not modify invoice or payment state.
4. The service does not move `BillingSchedule.next_run_date`.
5. Inactive schedules cannot generate charges.
6. Inactive occupancies cannot generate charges.
7. Charge date cannot precede occupancy check-in.
8. Charge generation is a domain operation, not an AI/automation source of financial truth.

## Architecture Rule

`BillingSchedule -> canonical charge-generation service -> Charge`

Future orchestration may call this service, but must not duplicate charge-creation rules.

## Completion Gate

Implementation + focused tests + migration-state check + full regression + CI GREEN.
