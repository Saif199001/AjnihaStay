# Phase 3.4 — Recurring Billing Foundation

**Status:** LOCKED  
**Phase:** 3.4  
**Depends on:** Phase 3.3 Payment Allocation

## Objective

Establish the durable domain foundation for recurring billing without changing the canonical financial truth established in Phase 3.3.

The foundation defines recurring billing configuration and scheduling intent. It does **not** itself create charges, invoices, payments, or allocations.

## Architecture

The intended future flow is:

`Occupancy + Billing Configuration → Billing Schedule → Charge Generation → Invoice Generation`

Recurring billing is an upstream configuration/scheduling layer. Financial state transitions remain owned by the existing canonical financial services.

## Current-domain audit

- `tenant.Occupancy` already contains billing type (`advance` / `arrears`), billing cycle (`monthly` / `daily`), rent, check-in/check-out, next due date, and active state.
- `tenant.Charge` already represents persisted charge facts with occupancy, charge type, description, amount, and charge date.
- `payments.Invoice` already represents invoice financial state.
- `payments.Payment` and `payments.PaymentAllocation` remain the canonical payment/allocation boundary from Phase 3.3.
- Therefore Phase 3.4 must **not** duplicate Occupancy billing-cycle data or create a parallel Charge/Invoice/Payment lifecycle.
- The recurring-billing model must be registered through the canonical Django `payments.models` module rather than an unregistered side module.

## In scope

1. A canonical `BillingSchedule` model owned by the payments domain.
2. Occupancy relationship with workspace isolation inherited through the occupancy → tenant → workspace chain.
3. Explicit recurrence frequency and next execution date.
4. Positive billing amount validation.
5. Active/inactive lifecycle state.
6. Validation that an active schedule belongs to an active occupancy and does not run before occupancy check-in.
7. Database constraints and indexes required for safe scheduling queries.
8. PostgreSQL RLS policy for workspace isolation.
9. Domain/API/service tests for validation, workspace isolation, and lifecycle behavior.
10. CI migration/RLS/test verification.

## Out of scope

- Automatic charge generation.
- Automatic invoice generation.
- Payment creation or payment allocation changes.
- Ledger/accounting implementation.
- Payment gateway integration.
- Recurring payment collection/autopay.
- Late fees, deposits, refunds, write-offs, reconciliation, or settlement redesign.
- AI or automation execution beyond the durable schedule foundation.
- Replacing existing Occupancy billing fields.
- Replacing or duplicating `tenant.Charge`.

## Financial invariants

1. A BillingSchedule is configuration/scheduling intent, not financial truth.
2. Creating or changing a BillingSchedule must not mutate Invoice, Payment, or PaymentAllocation state.
3. PaymentAllocation remains the canonical source for invoice-paid amounts.
4. Recurring billing must eventually call the canonical charge/invoice financial services rather than write financial state directly.
5. Workspace isolation is mandatory at ORM/domain and PostgreSQL RLS boundaries.
6. Existing Phase 0–3.3 behavior must remain unchanged.

## Implementation rules

- Do not introduce a parallel model-registration mechanism.
- Add the canonical model to `payments/models.py` unless a later architecture audit explicitly establishes a better existing domain boundary.
- Add a forward migration and corresponding RLS policy in the same implementation slice.
- Keep schedule execution separate from schedule persistence; no background runner is introduced in this foundation task.
- Preserve existing API response contracts unless a new recurring-billing endpoint is explicitly required by the locked scope.
- Follow the project implementation order: model → migration/RLS → domain service → API → focused tests → full regression → CI.

## Acceptance criteria

- BillingSchedule is discoverable by Django migrations and model checks.
- Invalid amounts, dates, inactive-occupancy activation, and invalid workspace access are rejected.
- Cross-workspace schedule reads/writes are blocked.
- PostgreSQL RLS is fail-closed and included in the protected-table configuration.
- Existing financial lifecycle and allocation tests remain green.
- No charge, invoice, payment, or allocation is created as a side effect of schedule persistence.
- Full CI is green on the final implementation commit.

## Completion gate

Phase 3.4 is **not COMPLETE** until the final implementation commit has:

1. migration graph validation,
2. migrations check,
3. RLS enable/force validation,
4. focused recurring-billing tests,
5. full Django regression suite,
6. Django system checks,
7. final security/data-integrity audit,
8. CI GREEN.

Only after all gates pass may this document be changed from `LOCKED` to `COMPLETE`.
