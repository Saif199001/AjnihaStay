# Phase 3.4-D — Invoice Generation Foundation

**Status: LOCKED**

## Objective
Establish one canonical domain-service seam for generating invoices from an occupancy billing period while preserving the existing financial lifecycle:

`Occupancy → Charge → Invoice → Payment`

The service must calculate invoice financial terms from authoritative occupancy and charge data, be workspace-scoped, be transaction-safe, and be idempotent for the same billing period.

## In scope
- Canonical invoice-generation domain service in `payments/`.
- Workspace-scoped occupancy resolution and row locking.
- Validation of occupancy state and billing-period dates.
- Invoice rent calculation from the occupancy rent.
- Invoice charge calculation from existing `tenant.Charge` records within the billing period.
- Idempotent generation for an already-created billing period.
- Preservation of existing invoice financial terms once payment/allocation activity exists.
- Refactoring the existing trusted recurring-invoice utility to delegate invoice creation to the canonical service, without creating a second invoice-generation authority.
- Focused service and regression tests.
- Migration-state verification; no schema migration is expected.

## Out of scope
- Payment creation or allocation.
- Changes to `Payment` or `PaymentAllocation` behavior.
- BillingSchedule cursor advancement inside the invoice-generation service.
- Scheduler/background infrastructure redesign.
- Public/manual invoice-create API enablement.
- New invoice schema, invoice-line model, tax/GST engine, discounts, credits, refunds, or ledger entries.
- Replacing the existing occupancy recurring-billing orchestration with BillingSchedule-driven orchestration.

## Invariants
1. Invoice financial truth remains owned by the canonical financial domain services.
2. Invoice generation is strictly workspace-scoped.
3. Occupancy must be active and the billing period must be valid for that occupancy.
4. `rent_amount` comes from the authoritative occupancy rent.
5. `charges_amount` comes from charges belonging to the same occupancy and billing period.
6. Invoice generation never creates payments or payment allocations.
7. Re-running generation for the same billing period must not create duplicate invoices.
8. Existing paid/allocated invoice financial terms must never be mutated by generation.
9. The canonical invoice service does not advance recurring-billing cursors; orchestration owns cursor movement.
10. Existing supported recurring invoice behavior must not regress.
11. Workspace isolation/RLS, transaction safety, and existing Phase 0–3.4-C contracts remain protected.
12. AI or automation may request generation, but cannot become the source of financial truth.

## Implementation rule
The existing `payments.utils.generate_recurring_invoices()` is an orchestration entry point, not a second financial authority. It must delegate invoice creation to the canonical invoice-generation service. Any recurring cursor advancement remains in the orchestration layer after successful generation.

## Completion gate
Phase 3.4-D is complete only after:
- implementation is committed;
- focused invoice-generation tests pass;
- recurring-invoice regression tests pass;
- `makemigrations --check --dry-run` confirms no unintended schema drift;
- full Django regression passes;
- CI is GREEN on the final commit;
- final financial/workspace-isolation audit is completed.
