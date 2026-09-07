# Phase 3.4 — Recurring Billing Foundation

**Status: LOCKED**

## Objective

Establish the durable recurring-billing configuration layer without changing the canonical financial truth established in Phase 3.3.

## Scope

- Persist a `BillingSchedule` against an existing `Occupancy`.
- Support the existing occupancy billing frequencies: daily and monthly.
- Validate positive schedule amounts.
- Prevent a schedule's next run date from preceding occupancy check-in.
- Prevent an active schedule on an inactive occupancy.
- Preserve workspace isolation through the occupancy → tenant → workspace relationship and workspace RLS.
- Provide manager-authorized schedule configuration APIs and staff read access.
- Keep schedule configuration free of financial side effects: creating or editing a schedule must not create charges, invoices, payments, or allocations.
- Establish a clean service boundary for future charge/invoice generation.

## Out of Scope

- Charge generation execution.
- Invoice generation execution.
- Payment allocation changes.
- Ledger/accounting/reconciliation.
- Payment gateways, UPI, notifications, or automation workers.
- Changing the existing Occupancy/Charge financial contract.
- Replacing the Phase 3.3 canonical allocation service.

## Financial Invariants

1. BillingSchedule is configuration, not financial state.
2. Schedule writes cannot directly change Invoice, Payment, PaymentAllocation, or Charge state.
3. A schedule belongs to exactly one occupancy and is therefore workspace-scoped through that occupancy's tenant.
4. Existing workspace RLS remains mandatory.
5. Existing validated payment, allocation, partial-payment, advance-payment, arrears, settlement, and dashboard behavior must not regress.

## Model-Change Audit Gate

Before every model-related change in this phase:

1. Inspect related models and all FK/M2M/OneToOne relationships.
2. Inspect related `related_name`, constraints, indexes, and model validation.
3. Inspect the existing migration files and migration graph/heads.
4. Compare model state with the latest migration state.
5. Verify generated index/constraint names before committing migrations.
6. Run `makemigrations --check --dry-run`, migration graph checks, migration application, focused tests, and full CI.

## Completion Gate

Phase 3.4 is complete only when schedule configuration behavior, security/isolation, regression tests, migration state, and CI are all green.

Only after this gate should charge/invoice generation work begin.
