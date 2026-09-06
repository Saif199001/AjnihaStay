# Phase 3.3-B — PaymentAllocation Canonical Service

**Status:** LOCKED
**Version:** v1.0
**Date:** 2026-09-07

## 1. Purpose

Phase 3.3-B introduces the canonical service boundary for allocating persisted payments to invoices. The service must support partial allocation, multi-invoice allocation, remaining/unallocated payment value, strict workspace isolation, transactional integrity, and concurrency safety without changing the historical meaning of `Payment.amount`.

Phase 3.3-A schema remains the compatibility foundation. Existing single-invoice payment behavior must continue to work until the later audit-remediation phase deliberately migrates legacy paths.

## 2. Locked Financial Semantics

`Payment.amount` is the immutable historical fact: the amount of money received.

`PaymentAllocation.amount` is the immutable invoice-specific settlement fact: how much of that payment is applied to one invoice.

Therefore:

```text
Payment.amount
    = total money received

SUM(PaymentAllocation.amount)
    = money allocated from that payment

Payment.amount - SUM(PaymentAllocation.amount)
    = unallocated remainder
```

For each invoice:

```text
SUM(valid PaymentAllocation.amount)
    = amount settled through allocations
```

`Invoice.paid_amount` and `Invoice.status` remain compatibility fields. Their authoritative transition remains inside the canonical financial service boundary and will become allocation-derived as part of the post-3.3-B remediation/read-model work.

## 3. Canonical Operation

The primary write operation is:

```python
allocate_payment(user, workspace, payment, allocations)
```

Conceptually:

```text
API / command / job
        ↓
Canonical Allocation Service
        ↓
transaction.atomic()
        ↓
validate workspace + input
        ↓
lock payment
        ↓
lock all affected invoices in deterministic ID order
        ↓
calculate current allocated / settled amounts
        ↓
validate all allocation caps
        ↓
create immutable allocation rows
        ↓
reconcile affected invoice compatibility state
        ↓
COMMIT
```

No API, serializer, model signal, dashboard, or direct model save may independently implement allocation state transitions.

## 4. Input Contract

The service receives:

- explicit `workspace`
- `actor/user`
- `payment` or payment ID
- one or more allocation instructions
- each instruction contains `invoice` and `amount`

The service must normalize invoice references to IDs before querying and must reject malformed/non-positive IDs.

Duplicate invoice instructions in one operation must be normalized or rejected deterministically; the implementation should prefer normalization by summing amounts for the same invoice before validation, provided this does not obscure caller errors.

## 5. Payment Invariants

The service must enforce:

```text
0 < allocation.amount
SUM(existing allocations) + SUM(new allocations) <= Payment.amount
```

The service must expose the remaining amount safely:

```text
unallocated = Payment.amount - allocated_amount
```

An allocation that exceeds the remaining payment amount is rejected. No silent over-allocation and no negative remainder are allowed.

`Payment.amount`, `Payment.invoice`, and `Payment.workspace` remain immutable after creation under the existing model boundary.

## 6. Invoice Invariants

For every affected invoice:

```text
SUM(existing allocations) + new allocation amounts <= Invoice.total_amount
```

An allocation exceeding invoice outstanding balance is rejected.

Invoice workspace must equal the explicit service workspace, and the payment workspace must equal the same workspace.

No cross-workspace payment/invoice allocation is permitted.

## 7. Multi-Invoice Allocation

A single payment may be allocated across multiple invoices:

```text
Payment ₹10,000
   ├── Invoice A ₹4,000
   ├── Invoice B ₹3,500
   └── Invoice C ₹2,000

Remaining = ₹500
```

The service must validate the complete requested operation before creating any allocation row. If any requested allocation fails validation, the entire transaction rolls back and no partial allocation is persisted.

## 8. Concurrency and Lock Ordering

All allocation writes must occur inside one database transaction.

The payment row must be locked before reading its available allocation capacity.

All affected invoice rows must be locked before calculating their available balances. Invoice IDs must be sorted ascending and locked in deterministic order to reduce deadlock risk when concurrent requests touch overlapping invoices.

The intended sequence is:

```text
BEGIN
  lock payment
  resolve affected invoice IDs
  lock invoices ORDER BY id
  calculate existing allocations
  validate payment capacity
  validate invoice capacity
  create allocations
  reconcile compatibility state
COMMIT
```

The implementation must not rely on thread execution order.

## 9. Transaction Atomicity

Allocation across multiple invoices is one financial operation.

Example:

```text
Payment ₹10,000
Invoice A accepts ₹4,000
Invoice B rejects ₹7,000 because only ₹6,000 remains
```

Result:

```text
NO allocation rows created
```

There must never be a partially persisted multi-invoice allocation operation.

## 10. Legacy Single-Invoice Compatibility

Existing `record_payment()` behavior remains intact during 3.3-B.

For legacy payments that already have `Payment.invoice`, historical backfilled `PaymentAllocation` rows represent the historical settlement relationship.

3.3-B must not silently reinterpret or rewrite historical payment facts.

A future remediation phase will migrate legacy invoice settlement calculations from `Payment.amount` to allocations after the allocation service is proven stable.

## 11. Invoice Compatibility-State Reconciliation

3.3-B may use a dedicated internal helper to reconcile affected invoices after successful allocations.

The reconciliation target is:

```text
paid_amount = SUM(valid allocations for invoice)

status:
  0       → pending
  partial → partial
  total   → paid
```

However, the implementation must preserve the Phase 3.2 rule that financial transitions have one canonical service owner. Reconciliation must not be implemented through model signals.

The exact migration of all read paths to allocation-derived state is a post-3.3-B remediation item.

## 12. API Contract

3.3-B should introduce the service first and test it independently.

API exposure must be thin:

```text
serializer
  → shape/basic validation

service
  → workspace/business validation
  → locking
  → allocation invariants
  → transaction
  → persistence
```

The API must not calculate payment remainder or invoice outstanding independently.

Existing payment creation/read contracts must remain backward compatible unless a deliberate contract change is separately approved.

## 13. Model Boundary

Models remain responsible for structural invariants:

- positive allocation amount
- immutable allocation fields
- payment/invoice workspace consistency
- database constraints
- deletion protection

Models must not become the financial orchestration layer.

QuerySet/bulk operations are not treated as a safe substitute for the canonical service.

## 14. Read Helpers

3.3-B should provide service-owned read helpers for:

- payment allocated amount
- payment unallocated amount
- invoice allocated/settled amount
- invoice outstanding amount

These helpers must use explicit workspace scope where applicable.

Dashboard and settlement consumers should not be migrated wholesale until the allocation write path and compatibility regression suite are green. That migration belongs to the post-3.3-B remediation phase.

## 15. Error Semantics

The service must reject deterministically:

- payment not found
- payment outside workspace
- invoice not found
- invoice outside workspace
- payment/invoice workspace mismatch
- malformed allocation input
- non-positive allocation
- payment over-allocation
- invoice over-allocation
- empty allocation request

Errors should use Django `ValidationError` consistent with the existing financial service boundary.

## 16. Idempotency / Duplicate Requests

Full external idempotency-key support is not part of 3.3-B unless already required by an existing API contract.

The service must nevertheless avoid accidental duplicate allocation through a single operation by validating and persisting all requested allocations atomically.

Future idempotency can add an operation key without changing the allocation model semantics.

## 17. Required Test Matrix

### Basic

- one payment → one invoice
- partial allocation
- full allocation
- payment remainder
- exact payment exhaustion

### Multi-invoice

- one payment → two invoices
- one payment → multiple invoices
- partial allocations across invoices
- duplicate invoice instructions
- zero/negative amount rejection

### Limits

- payment allocation exceeds remaining payment
- invoice allocation exceeds outstanding invoice amount
- exact boundary succeeds

### Workspace

- payment outside workspace
- invoice outside workspace
- cross-workspace allocation rejected

### Atomicity

- second allocation failure rolls back first allocation
- no partial rows after failed transaction

### Immutability

- allocation amount cannot change
- allocation payment cannot change
- allocation invoice cannot change

### Concurrency

- two concurrent allocations cannot over-allocate one payment
- two concurrent allocations cannot over-settle one invoice
- overlapping multi-invoice operations use deterministic lock ordering

### Regression

- existing payment creation remains green
- historical backfilled allocations remain intact
- settlement remains unchanged until planned read-model migration
- dashboard remains unchanged until planned migration

## 18. Non-Goals

3.3-B does not implement:

- `AdvanceCredit` entity
- refund lifecycle
- payment gateway webhooks
- recurring billing
- full ledger
- complete settlement lifecycle entity
- external idempotency infrastructure
- broad dashboard/read-model migration

Those remain separate milestones.

## 19. Implementation Sequence

1. Add canonical allocation service and private helpers.
2. Add allocation invariant and workspace tests.
3. Add multi-invoice atomicity tests.
4. Add concurrency tests using independent database connections.
5. Run full regression suite.
6. Expose API only after service tests are green.
7. Confirm CI green.
8. Perform 3.3-B deep audit.
9. Only after 3.3-B is green and audited, implement the deferred 3.3-A audit findings.

## 20. Exit Criteria

Phase 3.3-B is complete only when:

- allocation writes have one canonical service boundary
- payment capacity is enforced transactionally
- invoice capacity is enforced transactionally
- workspace isolation is enforced
- multi-invoice operations are atomic
- deterministic lock ordering is implemented
- concurrent allocation cannot over-allocate payment or invoice
- allocation rows are immutable
- historical data remains intact
- existing Phase 3.2 behavior remains green
- API delegates rather than owns financial logic
- CI is green
- deep audit finds no blocker

## 21. Locked Decision

**KEEP:** Phase 3.2 canonical financial boundary, Payment historical fact semantics, existing compatibility fields, workspace/RLS isolation, model-level defensive invariants, existing API contracts.

**EXTEND:** PaymentAllocation canonical write service, allocation-aware calculations, multi-invoice allocation, transactional/concurrency guarantees.

**DEFER:** AdvanceCredit, refunds, ledger, broad read-model migration, and the deferred Phase 3.3-A audit remediation until after 3.3-B is proven green.

**RULE:** No financial write path may bypass the canonical allocation service once an allocation is being created or changed.
