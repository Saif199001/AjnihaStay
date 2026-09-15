# AjnihaStay — Phase 3.9 Final Lock

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-10  
**Branch:** `phase-3.9/credits-debits-adjustments`

## 1. Purpose

This document closes Phase 3.9 after completion of the bounded Credits / Debits / Financial Adjustments and Payment Refund / Cash Reversal Event scope.

The locked product source of truth remains `docs/BLUEPRINT.md`. The Phase 3 financial architecture remains authoritative for financial mutation and reporting boundaries.

## 2. Completed Scope

### 3.9-A — FinancialAdjustment

- Immutable financial adjustment event model.
- Credit, debit, discount, waiver and write-off types.
- Positive two-decimal monetary amount and required reason.
- Workspace ownership and PostgreSQL RLS.
- Workspace-scoped idempotency.
- Canonical adjustment service and API.
- Manager-level financial mutation authorization.

### 3.9-B — Canonical Financial Position Integration

- Canonical invoice financial-position calculation.
- Gross receivable + debit adjustments - reducing adjustments.
- Outstanding derived after PaymentAllocation and AdvanceCreditApplication.
- Invoice compatibility state reconciled from canonical position.
- Shared validation across payment, allocation, advance-credit and settlement flows.
- Historical payment/allocation records remain immutable.

### 3.9-C — Payment Refund / Cash Reversal Event

- Payment-centric `PaymentRefund` event model.
- Full, partial and multiple partial refunds.
- Refund capacity based on payment amount minus successful refunds and active reservations.
- Requested/processing refunds reserve capacity.
- Failed refunds release reserved capacity.
- Successful refunds permanently consume capacity.
- Immutable financial history and controlled lifecycle:
  `requested → processing → succeeded`
  `requested/processing → failed`
- Payment-row locking for refund-capacity serialization.
- Workspace-scoped idempotency with database uniqueness and race handling.
- Owner/admin/manager authorization through workspace membership.
- Provider-neutral service and API boundary.
- Refund does not mutate Payment, PaymentAllocation, AdvanceCredit or Invoice status.

## 3. Regression / Safety Boundaries

The following principles are locked:

1. Business events enter canonical financial services.
2. Model `save()`, signals, API handlers and provider callbacks are not competing financial truth.
3. Historical Payment and PaymentAllocation records are immutable.
4. A refund represents cash returned from a payment; it is not a receivable-side credit adjustment.
5. A refund is payment-centric because one payment may cover multiple invoices.
6. Refund allocation attribution and accounting/ledger treatment remain future reconciliation concerns.
7. AdvanceCredit refund/redemption and customer wallet/refundable-balance semantics are outside this phase.
8. Credit-note lifecycle, tax/GST accounting, GL ledger and bank reconciliation are outside this phase.
9. Invoice status remains the existing compatibility model and is not redefined as a refund state machine.
10. Workspace isolation is required at API/service/database layers.

## 4. Test / CI Gate

The final implementation head is:

```text
e549b2fb31eb1425a6bd64340db720d03fe86427
```

The corresponding GitHub Actions Django CI run is:

```text
CI #356
Run ID: 34442621919
Event: push
Conclusion: success
```

The CI run was executed against the exact final implementation head above and completed successfully.

## 5. Deferred Items

Phase 3.9 does not include:

- Dashboard canonical-financial reporting remediation (B1).
- Deterministic recurring invoice generation (B2).
- Occupancy concurrency hardening (B3).
- FinancialAdjustment idempotency race hardening (B4).
- Service-layer authorization consistency outside the bounded 3.9 services (B5).
- Broader forensic/CI gate work (B6).
- Accounting/GL ledger.
- Bank reconciliation.
- Refund reversal implementation.
- Chargebacks/disputes.
- Gateway-specific refund business logic.
- Customer wallet/refundable balance.
- Advance-credit refund/redemption.
- Credit-note lifecycle.
- Tax/GST accounting.
- Approval thresholds / maker-checker workflow.
- Bulk financial workflows.

These remain separately scoped and must not be introduced implicitly into this lock.

## 6. Final Result

**PHASE 3.9 — COMPLETE / LOCKED**

All bounded Phase 3.9 financial-adjustment and refund capabilities are implemented without replacing existing financial history or creating a competing financial truth.

Next execution stage is the already-approved forensic remediation sequence:

`B1 → B2 → B3 → B4 → B5 → B6`

Only after the B1–B6 gate is green should Phase 3.10 begin.
