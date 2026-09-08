# AjnihaStay — Phase 3.9 Credits / Debits / Financial Adjustments

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-09  
**Branch:** `phase-3.9/credits-debits-adjustments`

## Purpose

Phase 3.9-A and 3.9-B establish the first controlled receivable-side adjustment layer without replacing the existing Charge → Invoice → Payment, PaymentAllocation, or AdvanceCredit workflows.

This document is the final implementation/audit lock for the bounded Phase 3.9-A/B scope.

---

## 1. Scope Locked

### 3.9-A — FinancialAdjustment Model + Migration

Implemented and audited:

- `FinancialAdjustment` financial-event model.
- Adjustment types:
  - `credit`
  - `debit`
  - `discount`
  - `waiver`
  - `write_off`
- Positive monetary amount with two-decimal database precision.
- Required non-blank reason.
- Optional reference.
- Workspace-scoped idempotency key.
- `created_by` audit actor.
- `PROTECT` relationships for financial history.
- Immutable financial records after creation.
- Cross-workspace invoice validation.
- Database constraints for amount, type, reason and idempotency uniqueness.
- Workspace/invoice and reporting-oriented indexes.
- PostgreSQL RLS enabled and forced with workspace isolation policy.

### 3.9-B — Canonical Financial Adjustment Service + API

Implemented and audited:

- Canonical `create_financial_adjustment()` service.
- Canonical `calculate_invoice_financial_position()` helper.
- Manager-level mutation authorization: owner/admin/manager only.
- Workspace-scoped invoice lookup.
- Invoice row locking with `select_for_update()` for same-invoice mutation serialization.
- Credit-side adjustment validation against remaining collectible balance.
- Debit-side receivable expansion.
- Distinct treatment of credit, discount, waiver and write-off while aggregating them on the reducing side.
- PaymentAllocation and AdvanceCreditApplication remain cash/prepaid settlement records and are not mutated by adjustment creation.
- Compatibility `Invoice.paid_amount` and `Invoice.status` are reconciled from canonical financial position.
- Idempotent retry returns the original adjustment when the operation payload matches.
- Idempotency-key conflict is rejected when the operation differs.
- Dedicated API serializer, endpoint and route.
- API validation occurs before financial mutation.
- API returns the created/reused adjustment and canonical financial position.
- API and service both enforce authorization/workspace boundaries.

---

## 2. Canonical Financial Equation

The locked Phase 3.9-A/B position is:

```text
Gross Receivable
+ Debit Adjustments
- Credit Adjustments
= Adjusted Receivable

Adjusted Receivable
- Payment Allocations
- Advance Credit Applications
= Outstanding
```

Where the reducing adjustment bucket currently contains:

```text
Credit + Discount + Waiver + Write-off
```

Payment and advance-credit application remain settlement concepts. An adjustment does not rewrite historical cash records.

---

## 3. Invoice State Rules

The canonical helper derives compatibility invoice state from the financial position:

- `pending`: no settlement against a positive receivable.
- `partial`: settlement is positive but does not fully settle a positive adjusted receivable.
- `paid`: settlement equals a positive adjusted receivable.
- A zero/non-positive collectible balance produced only by adjustment does **not** masquerade as cash collection; it remains `pending` in the current legacy state model.

This preserves the distinction between receivable reduction and cash settlement while the future ledger/status model is developed.

---

## 4. Security / Multi-Tenancy Audit

### PASS

1. Service mutations require active workspace membership with owner/admin/manager role.
2. API uses the existing `WorkspaceManagerPermission` and the canonical service performs a second authorization check.
3. Invoice lookup is explicitly scoped to the supplied workspace.
4. FinancialAdjustment itself carries workspace ownership.
5. PostgreSQL RLS is enabled and forced for the adjustment table.
6. Cross-workspace API/service attempts are covered by tests and do not mutate data.
7. Historical Payment, PaymentAllocation and AdvanceCredit records are not edited by adjustment creation.
8. Adjustment records are immutable through the model save path.

No security check was weakened or bypassed to satisfy tests.

---

## 5. Integrity / Concurrency Audit

### PASS

- Same-invoice financial mutations are serialized by locking the invoice row inside the canonical transaction.
- The collectible-balance check and adjustment creation occur inside the same transaction.
- Idempotency is enforced at both service level and database level.
- Duplicate idempotency-key conflicts are deterministic for serialized same-invoice operations.
- Migration graph is clean and reproducible.
- RLS migration step is exercised in CI.

### Known boundary for future hardening

The current idempotency design is workspace-scoped and database-unique. Concurrent identical requests targeting different invoices can still race at the unique constraint because the invoice-row lock is naturally invoice-specific. Phase 3.9-C or a later financial hardening task may introduce a dedicated idempotency-event primitive if stronger cross-invoice concurrency semantics become necessary.

This is a bounded future hardening item, not a Phase 3.9-A/B correctness blocker.

---

## 6. API Contract Audit

The locked create endpoint is:

```text
POST /api/financial-adjustments/create/
```

Request contract:

```json
{
  "invoice": 123,
  "adjustment_type": "credit",
  "amount": "1000.00",
  "reason": "Approved adjustment",
  "reference": "CASE-123",
  "idempotency_key": "ADJ-CASE-123"
}
```

Contract rules:

- Invoice ID must be positive.
- Adjustment type must be one of the locked types.
- Amount must be positive and limited to two decimal places at the API boundary.
- Reason must be non-blank.
- Reference and idempotency key are optional.
- Unauthorized/staff mutation is rejected.
- Cross-workspace invoice is not exposed as a valid mutation target.
- Valid creation returns HTTP 201.
- Idempotent replay returns the existing adjustment without creating a second record.

---

## 7. Regression / Integration Audit

The adjustment service is now the shared financial-position authority used by:

- invoice state reconciliation,
- payment acceptance/outstanding validation,
- final settlement calculations,
- payment allocation validation/reconciliation,
- advance-credit application validation.

This is important: Phase 3.9-B does not create a parallel financial truth. Existing financial workflows consume the same canonical adjusted position.

---

## 8. Test Coverage Audit

Covered scenarios include:

- initial gross receivable,
- credit adjustment,
- debit adjustment,
- discount,
- waiver,
- write-off,
- partial payment plus credit,
- partial payment plus debit,
- excessive reducing adjustment rejection,
- fully settled invoice adjustment rejection,
- zero collectible balance without cash remaining non-paid,
- idempotent replay,
- idempotency conflict,
- manager-level authorization,
- cross-workspace service isolation,
- API creation,
- API replay,
- API permission rejection,
- API cross-workspace isolation,
- invalid API payload rejection.

---

## 9. CI Gate — GREEN

Latest verified Phase 3.9-A/B head:

```text
44748bce6cd7805fa48a9cb82cec329dea01588d
```

Latest verified workflow run:

```text
CI #328
Run ID: 34269871448
Job: Django checks and tests
Conclusion: success
```

Verified successful stages include:

- migration graph check,
- `makemigrations --check --dry-run`,
- migrations apply,
- workspace RLS enable/force,
- full Django test suite,
- Django system checks.

Therefore the Phase 3.9-A/B implementation satisfies the CI gate for this lock.

---

## 10. Explicit Non-Goals / Deferred Items

The following are **not** silently included in Phase 3.9-A/B:

- customer wallet/refundable balance,
- refunds and cash reversals,
- payment-gateway reversal flows,
- accounting/GL ledger,
- bank reconciliation,
- tax/GST adjustment accounting,
- late-fee engine,
- credit-note document lifecycle,
- UI/admin workflow,
- bulk adjustment workflows,
- dedicated approval workflow,
- cross-invoice idempotency-event infrastructure.

These require separate architectural decisions.

---

## 11. Architecture Lock Decisions

The following decisions are now locked for Phase 3.9-A/B:

1. **Adjustment is a receivable-side event**, not a payment and not an advance credit.
2. **Historical payment/allocation records are immutable and are not rewritten by adjustments.**
3. **Reducing adjustments cannot exceed the remaining collectible balance.**
4. **Full reduction without cash settlement is not represented as a cash-paid event.**
5. **Manager-level access is required for financial adjustment mutation.**
6. **Workspace isolation is mandatory at service, API and RLS layers.**
7. **Idempotency is part of the financial mutation contract.**
8. **The canonical financial-position helper is the shared read authority for current invoice receivable/settlement state.**
9. **Existing Charge → Invoice → Payment, allocation, advance-credit and settlement workflows remain preserved.**
10. **No Phase 3.9-C feature may reinterpret these records without an explicit architecture decision.**

---

## 12. Audit Result

**PHASE 3.9-A: PASS — LOCKED**  
**PHASE 3.9-B: PASS — LOCKED**

The bounded implementation is production-architecture ready for the next investigation stage. Any new financial behavior must first be mapped against this locked model and the existing Phase 3 financial architecture.

**Next stage:** Phase 3.9-C architecture investigation only. No implementation should begin until its domain boundary, financial semantics, authorization, idempotency, concurrency, ledger implications and regression impact are investigated and explicitly locked.
