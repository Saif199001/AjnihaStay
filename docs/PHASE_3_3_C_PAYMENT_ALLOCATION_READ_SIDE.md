# Phase 3.3-C — Payment Allocation Read-Side Canonicalization

**Status: COMPLETE**  
**Branch:** `phase-1/workspace-multitenancy`  
**Phase:** 3 — Financial Architecture  
**Depends on:** Phase 3.3-A and Phase 3.3-B

## 1. Objective

Make `PaymentAllocation` the canonical read-side representation of invoice-paid financial state while preserving all currently supported payment workflows and compatibility fields.

The system must follow:

`Payment / Business Event → Canonical Allocation Service → PaymentAllocation → Invoice financial state → Read models`

`Invoice.paid_amount` and `Invoice.status` remain compatibility/materialized state only. They must never become an independent source of truth.

## 2. In Scope

### 2.1 Canonical financial reads

- Invoice paid amount calculations must derive from persisted `PaymentAllocation` rows.
- Invoice outstanding/due calculations must be allocation-aware.
- Payment allocation totals must be capacity-safe against `Payment.amount`.
- Existing settlement/read calculations that represent collected money must use allocations rather than raw `Payment.amount`.

### 2.2 Dashboard/read-model migration

- Dashboard collection totals must become allocation-aware.
- Dashboard outstanding and overdue calculations must no longer depend on legacy `Invoice.paid_amount` as financial truth.
- Existing dashboard response shape must be preserved unless a contract requires otherwise.
- Workspace isolation must remain intact.

### 2.3 Payment compatibility

- Existing invoice-linked payments remain valid.
- Existing advance/unallocated payments remain valid.
- `Payment.amount` remains the total payment capacity.
- `PaymentAllocation.amount` represents the amount applied to a specific invoice.
- No destructive migration of historical payment data.

### 2.4 State consistency

- Canonical service paths must update allocation rows and reconcile compatibility invoice state atomically.
- Direct mutation of persisted allocation payment/invoice/amount fields remains prohibited.
- Financial calculations must not double-count an invoice-linked payment and its allocation.

### 2.5 Integrity / security / concurrency

- Workspace isolation and RLS remain mandatory.
- Existing allocation concurrency guarantees remain mandatory.
- Existing API/RBAC contracts remain mandatory.
- Multi-invoice allocation remains atomic.

## 3. Explicitly Out of Scope

3.3-C does **not** implement:

- recurring billing
- charge generation
- invoice generation redesign
- credits/debits
- refunds
- deposits redesign
- late-fee engine
- write-offs
- settlement entity/workflow redesign
- ledger/accounting engine
- reconciliation engine
- India gateway/UPI integrations
- WhatsApp/SMS/email integrations
- AI financial decisions

Those remain later Phase 3/Phase 4 work.

## 4. Locked Invariants

1. `Payment.amount` is payment capacity, not invoice-paid truth.
2. `SUM(PaymentAllocation.amount)` for an invoice is the canonical amount paid against that invoice.
3. `SUM(PaymentAllocation.amount)` for a payment must never exceed `Payment.amount`.
4. An allocation may only connect payment and invoice inside the same workspace.
5. Existing invoice-linked payments must not be double-counted through both `Payment.amount` and allocation rows.
6. Unallocated payments are legitimate and must remain supported.
7. Invoice paid/status compatibility fields must remain synchronized with canonical allocations on canonical mutation paths.
8. Read models must consume canonical allocation truth.
9. No supported Phase 0–3.3-B behavior may regress.
10. All changes must pass the project's relevant test suite and CI before 3.3-C is marked complete.

## 5. Acceptance Criteria

### Financial correctness

- Partial payment produces correct allocation-derived paid and due amounts.
- Full payment produces correct allocation-derived paid and due amounts.
- Multiple payments against one invoice aggregate correctly.
- One payment allocated across multiple invoices aggregates correctly per invoice.
- Unallocated payment contributes to payment capacity but not to invoice-paid totals until allocated.
- Invoice-linked historical payments are represented without double counting.

### Read-side correctness

- Dashboard `period_collected` uses allocations associated with payments whose payment date falls in the selected period.
- Dashboard outstanding and overdue values derive from allocation totals.
- Final settlement/read calculations derive collected amounts from allocations.

### Security and integrity

- Cross-workspace reads/writes remain rejected.
- Allocation mutation bypasses remain blocked.
- Existing concurrency tests remain green.
- Existing API/RBAC tests remain green.

### Regression

- Existing payment creation behavior remains functional.
- Existing partial-payment behavior remains functional.
- Existing advance/unallocated payment behavior remains functional.
- Existing arrears/outstanding behavior remains functional.

## 6. Implementation Rule

Do not broaden scope during implementation. If a discovered issue belongs to a later financial milestone, document it and defer it rather than implementing it opportunistically.

## 7. Completion Gate

3.3-C was changed from **LOCKED** to **COMPLETE** after implementation, focused allocation/read-side coverage, full regression CI, and final blueprint-compliance audit. The final documentation commit itself must still pass CI before the milestone is considered release-green.

## 8. Final Audit Record

- Canonical invoice paid/due reads: allocation-aware.
- Dashboard collection, outstanding, and overdue reads: allocation-aware.
- Final settlement collected amount: allocation-aware.
- Payment compatibility and unallocated-payment semantics: preserved.
- Allocation workspace integrity and immutable persisted allocation fields: preserved.
- Allocation API/RBAC/concurrency coverage: present and part of the verified regression suite.
- CI run #212 on the implementation commit: **GREEN**.
- Final documentation commit: triggers the required completion-gate CI verification.
