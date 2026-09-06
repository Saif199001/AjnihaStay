# Phase 3.3 — Payment Allocation Architecture

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-06  
**Branch:** `phase-1/workspace-multitenancy`

## 1. Purpose

Phase 3.3 extends the Phase 3.2 canonical financial boundary so that one payment can settle one or more invoices without changing the historical meaning of `Payment.amount`.

Phase 3.3 is the allocation layer only. Advance-credit, refunds, adjustments, recurring billing, gateway webhooks, and a full ledger remain later phases.

## 2. Non-negotiable preservation

The following existing behavior remains protected:

- Workspace/RLS isolation.
- Property → Unit → SubUnit → Occupancy relationships.
- Existing Invoice fields and API compatibility where practical.
- Existing Payment fields and historical payment facts.
- `Payment.amount` is the amount actually received, not an invoice settlement amount.
- Existing payment methods and payment dates.
- Partial and full settlement semantics.
- Canonical financial service ownership established in Phase 3.2.
- Transactional/concurrency guarantees.
- Settlement and dashboard behavior must not regress while the read model is migrated.
- No UI changes.
- No PR/merge as part of implementation unless explicitly requested.

## 3. Core financial model

### Current

```text
Payment → exactly one Invoice
```

### Phase 3.3 target

```text
Payment
   │
   ├── PaymentAllocation → Invoice A
   ├── PaymentAllocation → Invoice B
   └── unallocated remainder
```

For a payment of ₹10,000:

```text
Payment.amount                         = ₹10,000
Allocation(invoice A)                  = ₹6,000
Allocation(invoice B)                  = ₹3,000
Unallocated remainder                   = ₹1,000
```

The unallocated remainder is computed as:

```text
Payment.amount - SUM(PaymentAllocation.amount)
```

No separate `AdvanceCredit` model is introduced in Phase 3.3. The remainder is explicitly unallocated and becomes the future input for AdvanceCredit.

## 4. Payment model evolution

### Decision: Payment becomes invoice-independent at the domain level

The existing `Payment.invoice` foreign key is currently required. That shape cannot support a payment split across multiple invoices or a payment with no allocation.

Phase 3.3 will therefore migrate it to:

- `Payment.workspace` — required, explicit tenant boundary.
- `Payment.invoice` — nullable legacy compatibility field.

`Payment.workspace` is required because an unallocated payment cannot derive workspace ownership from an invoice.

### Meaning of `Payment.invoice`

During migration:

- Existing rows keep their invoice.
- The legacy single-invoice payment API continues to work.
- A legacy payment created against one invoice creates a corresponding `PaymentAllocation` for that invoice.
- New multi-invoice payments do not use `Payment.invoice` as financial source of truth.
- New unallocated payments may have `invoice=NULL`.
- Allocation rows are the authoritative invoice-settlement relationship.

The field is retained for backward API compatibility and migration safety, not as the future financial authority.

## 5. PaymentAllocation model

The model will contain at minimum:

```text
PaymentAllocation
-----------------
payment       FK → Payment
invoice       FK → Invoice
amount        Decimal
created_at    DateTime
```

Recommended relationships:

```text
Payment.allocations
Invoice.allocations
```

Foreign-key deletion behavior:

- Payment → PROTECT
- Invoice → PROTECT

Financial records must not disappear through ordinary parent deletion.

## 6. Allocation invariants

Every allocation must satisfy all of the following:

1. `amount > 0`.
2. Payment and Invoice belong to the same workspace.
3. Allocation amount cannot exceed the payment's currently unallocated amount.
4. Allocation amount cannot make invoice allocated total exceed invoice total.
5. Payment amount itself is immutable after creation.
6. Existing allocations are immutable in amount/payment/invoice through normal model save.
7. Allocation creation happens only through the canonical financial service.
8. No allocation is created without a valid Payment and Invoice.
9. No cross-workspace allocation is accepted.
10. Database constraints enforce local positive-amount invariants; service logic enforces aggregate invariants.

Aggregate invariants:

```text
SUM(PaymentAllocation.amount WHERE payment=P) <= P.amount

SUM(PaymentAllocation.amount WHERE invoice=I) <= I.total_amount
```

The remaining unallocated amount is always non-negative.

## 7. Invoice financial state

After Phase 3.3, invoice settlement state must no longer be derived from `Payment.amount`.

Canonical formula:

```text
allocated_paid = SUM(PaymentAllocation.amount)

outstanding = max(Invoice.total_amount - allocated_paid, 0)
```

Compatibility fields remain:

```text
Invoice.paid_amount = allocated_paid
Invoice.status      = derived from allocated_paid
```

Status rules remain:

```text
allocated_paid == 0                  → pending
0 < allocated_paid < total_amount   → partial
allocated_paid == total_amount       → paid
```

`Invoice.paid_amount` and `Invoice.status` remain compatibility/read-model fields owned by the canonical financial service.

## 8. Canonical operations

Phase 3.2 established:

```text
record_payment(...)
recalculate_invoice_state(...)
```

Phase 3.3 extends the canonical boundary with:

```text
record_payment(..., allocations=...)
allocate_payment(...)
```

### `record_payment`

Responsibilities:

- Validate workspace.
- Validate payment facts.
- Create immutable Payment fact.
- If the legacy single-invoice input is used, create its matching allocation atomically.
- If allocation instructions are supplied, validate all invoices and create all allocations atomically.
- Recalculate every affected invoice from allocations.
- Reject over-allocation before commit.

### `allocate_payment`

Responsibilities:

- Lock the payment.
- Lock every affected invoice in deterministic ID order.
- Validate workspace consistency.
- Calculate payment unallocated remainder from allocation rows.
- Validate each invoice's remaining balance.
- Create allocations atomically.
- Recalculate affected invoice states.

No API/view/model signal may independently perform these transitions.

## 9. Transaction and concurrency strategy

All allocation writes are atomic.

For an allocation command:

```text
BEGIN
  SELECT payment FOR UPDATE
  validate payment workspace
  identify affected invoices
  SELECT invoices FOR UPDATE ORDER BY id
  validate all allocation amounts
  create allocation rows
  recalculate affected invoices
COMMIT
```

### Deterministic lock ordering

When multiple invoices are involved, invoice rows must always be locked in ascending primary-key order.

This is mandatory to reduce deadlock risk when two concurrent payments allocate against overlapping invoice sets.

Example:

```text
Request A: Invoice 2 + Invoice 7
Request B: Invoice 7 + Invoice 2

Both acquire locks as:
Invoice 2 → Invoice 7
```

The service must never rely on caller-provided allocation order for lock ordering.

## 10. Payment creation compatibility

Existing API clients may continue sending:

```json
{
  "invoice": 123,
  "amount": "5000.00",
  "payment_method": "upi",
  "payment_date": "2026-09-06"
}
```

The canonical service will interpret this as:

```text
Create Payment
        ↓
Create PaymentAllocation(payment, invoice=123, amount=5000)
        ↓
Recalculate Invoice
```

This preserves the existing API contract while moving financial truth to allocations.

A new allocation-aware command may accept:

```json
{
  "amount": "10000.00",
  "payment_method": "upi",
  "payment_date": "2026-09-06",
  "allocations": [
    {"invoice": 123, "amount": "6000.00"},
    {"invoice": 124, "amount": "3000.00"}
  ]
}
```

The remaining ₹1,000 is unallocated.

## 11. Unallocated payments

Phase 3.3 does not create an AdvanceCredit entity.

Instead:

```text
unallocated_amount = payment.amount - sum(payment.allocations.amount)
```

Rules:

- It may be zero.
- It may be positive.
- It may never be negative.
- It is not silently assigned to an invoice.
- It is not silently discarded.
- It is not treated as invoice-paid money.

Future Phase 3.x work can convert explicitly approved unallocated amounts into `AdvanceCredit` records.

## 12. Workspace and RLS isolation

Workspace must be explicit on Payment after migration.

Canonical service validation must require:

```text
Payment.workspace == Invoice.occupancy.tenant.workspace
```

for every allocation.

RLS remains defense in depth. Application-level workspace validation remains mandatory even where database policies provide protection.

A payment from workspace A must never allocate to an invoice from workspace B.

## 13. Model responsibilities

Models enforce structural invariants only:

- positive allocation amount;
- valid required relationships;
- immutable financial identity/amount after creation where applicable;
- database constraints.

Models do **not** calculate invoice paid state from payment rows.

Models do **not** orchestrate multi-invoice allocation.

Signals remain non-authoritative and must not be required for financial correctness.

## 14. Read-model migration

The following must eventually use allocation-aware calculations:

- Invoice `paid_amount` / `due_amount` compatibility state.
- Settlement `total_paid` / `total_due`.
- Dashboard `period_collected`.
- Dashboard outstanding/overdue.
- Payment/invoice detail reads where settlement amounts are displayed.

During migration, existing compatibility fields may remain populated by the canonical service.

Once allocation support is stable, all financial reporting must converge on allocation-aware read services rather than treating `Payment.amount` as invoice-specific.

## 15. Settlement impact

Current settlement aggregates Payment rows directly. That is valid only while every Payment belongs to exactly one invoice.

After multi-invoice allocation is introduced, settlement must aggregate allocations associated with the occupancy's invoices:

```text
Occupancy invoices
        ↓
PaymentAllocations
        ↓
SUM(allocation.amount)
```

An unallocated payment must not reduce an occupancy invoice balance until explicitly allocated.

Security-deposit behavior remains unchanged in Phase 3.3.

## 16. Dashboard impact

The dashboard remains read-only.

Financial metrics must not be mutated by dashboard code.

After allocation support:

```text
Collected = allocation-aware payment settlement
Outstanding = invoice total - allocated paid
Overdue = allocation-aware outstanding for overdue invoices
```

The migration must preserve current outputs for all existing single-invoice payment data.

## 17. Migration strategy

Migration must be staged to avoid breaking existing production data.

### Step 1 — Schema preparation

- Add `Payment.workspace` as nullable temporarily.
- Backfill workspace from `Payment.invoice → Invoice → Occupancy → Tenant → Workspace`.
- Add `PaymentAllocation` table.
- Make Payment.invoice nullable only after compatibility handling is prepared.

### Step 2 — Historical backfill

For every existing Payment:

```text
Payment(amount=X, invoice=I)
        ↓
PaymentAllocation(payment=P, invoice=I, amount=X)
```

Backfill must be idempotent and preserve exact Decimal amounts.

### Step 3 — Constraints

After successful backfill:

- enforce Payment.workspace non-null;
- enforce PaymentAllocation positive amount;
- add useful indexes;
- retain Payment.invoice nullable for compatibility.

### Step 4 — Canonical service migration

Move payment acceptance to allocation-aware `record_payment()`.

Legacy one-invoice calls create one allocation.

### Step 5 — Read-model migration

Change invoice state, settlement, and dashboard calculations to use allocations.

### Step 6 — Regression proof

Prove that all existing single-invoice payments produce identical financial results before and after allocation migration.

## 18. API contract strategy

Existing endpoints remain compatible where possible.

New allocation functionality must be additive rather than requiring an immediate client rewrite.

API responsibilities:

- parse request shape;
- validate basic types/positive values;
- delegate financial decisions to canonical service;
- return canonical service errors consistently.

API must not:

- calculate outstanding balance independently;
- update Invoice.paid_amount/status directly;
- create PaymentAllocation rows directly;
- accept client-supplied paid/status as authority.

## 19. Refund and adjustment hooks

Phase 3.3 does not implement refunds or adjustments.

The design must leave room for future immutable financial events:

```text
Payment
  ↓
Allocation
  ↓
Refund / reversal / adjustment
```

Future reversals must not mutate historical Payment.amount to pretend the original payment never happened.

## 20. Test contract

Required tests before Phase 3.3 is considered complete:

### Allocation basics

- one payment → one invoice;
- one payment → multiple invoices;
- one invoice → multiple payments/allocations;
- partial allocation;
- exact full allocation;
- unallocated remainder;
- zero allocation rejected;
- negative allocation rejected.

### Aggregate invariants

- payment allocations cannot exceed Payment.amount;
- invoice allocations cannot exceed Invoice.total_amount;
- multiple allocations cannot overpay an invoice;
- Payment.amount remains unchanged;
- allocations remain immutable through normal model save.

### Workspace

- cross-workspace payment/invoice allocation rejected;
- cross-workspace read isolation;
- RLS regression remains green.

### Canonical ownership

- API delegates to canonical service;
- model save does not reconcile financial state;
- signals are not required;
- direct ORM allocation does not become an alternative financial state machine;
- compatibility `record_payment(invoice=...)` creates the expected allocation.

### Concurrency

- concurrent allocations cannot over-allocate a payment;
- concurrent allocations cannot overpay an invoice;
- overlapping multi-invoice requests use deterministic lock ordering;
- outcomes are order-independent.

### Read models

- invoice paid/status equals allocation totals;
- settlement uses allocations;
- dashboard preserves existing single-invoice results;
- unallocated payment does not reduce invoice outstanding.

### Migration

- all historical payments receive exactly one matching allocation;
- historical totals remain unchanged;
- migration is safe and deterministic.

## 21. Phase 3.3 non-goals

Do not implement in this phase:

- AdvanceCredit entity;
- refund lifecycle;
- payment gateway/webhook integration;
- recurring billing scheduler;
- tax engine;
- late-fee engine;
- adjustment engine;
- full accounting ledger;
- complete settlement lifecycle entity;
- UI changes.

## 22. Exit criteria

Phase 3.3 is complete only when:

1. PaymentAllocation exists with correct invariants.
2. Payment has explicit workspace ownership.
3. Legacy Payment.invoice compatibility is preserved safely.
4. Payment.amount remains the immutable payment fact.
5. Invoice settlement is allocation-driven.
6. Multi-invoice allocation works atomically.
7. Unallocated remainder is explicit and never silently assigned.
8. Deterministic invoice locking prevents allocation races/deadlocks.
9. Workspace/RLS isolation is green.
10. Settlement and dashboard are allocation-aware without regression.
11. Existing payment API behavior remains compatible.
12. Full regression + concurrency + migration tests are green.
13. CI is green.
14. No UI changes were introduced.

## 23. Final architectural lock

**KEEP:** Phase 3.2 canonical financial service and existing financial semantics.  
**EXTEND:** Payment with explicit workspace, PaymentAllocation, allocation-aware state/read models.  
**MIGRATE:** historical Payment → Invoice relationships into allocations.  
**PROTECT:** Payment.amount as the historical payment fact.  
**DO NOT:** create competing financial state machines in models, APIs, signals, dashboard, or settlement code.

Phase 3.3 implementation may begin only from this architecture.
