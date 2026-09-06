# AjnihaStay — Phase 3.2 Canonical Financial Transition Service

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-06  
**Branch:** `phase-1/workspace-multitenancy`

## Purpose

Phase 3.2 defines the canonical service boundary for financial state transitions before any PaymentAllocation, advance-credit, recurring billing, or ledger implementation is introduced.

The goal is to remove competing financial truth from model methods, signals and API handlers while preserving all currently supported financial behavior.

---

## 1. Core Decision

Financial mutations must flow through a canonical application/domain service.

```text
API / Command / Job / Webhook
             ↓
      Canonical Financial Service
             ↓
       Transaction Boundary
             ↓
       Domain Validation
             ↓
      Financial State Change
             ↓
       Persisted Records
```

The API layer must not independently calculate or mutate financial state.

Models remain responsible for structural validation and database constraints. They are not the orchestration authority for payment state transitions.

---

## 2. Current State to Preserve

The current system supports:

- Invoice creation as a primitive
- Invoice total derived from rent + charges
- Pending / partial / paid invoice status
- Partial payments
- Full payments
- Overpayment rejection
- Workspace-scoped payment creation
- Transactional invoice locking during payment creation
- Settlement calculation from actual payment rows

These behaviors become regression contracts for the new service.

---

## 3. Canonical Operations

Phase 3.2 establishes the service vocabulary.

### Invoice operations

```text
create_invoice(...)
recalculate_invoice_state(...)
```

### Payment operations

```text
record_payment(...)
```

### Settlement operation

```text
calculate_final_settlement(...)
```

`record_payment()` is the critical canonical transition for the current phase.

Future operations will extend this service boundary:

```text
allocate_payment(...)
create_advance_credit(...)
apply_advance_credit(...)
create_adjustment(...)
refund_payment(...)
close_settlement(...)
```

---

## 4. Payment State Transition

Current behavior is retained:

```text
Invoice outstanding = Total - Current valid payments

record_payment(amount)
        ↓
lock invoice
        ↓
validate amount
        ↓
create payment
        ↓
recalculate financial state
        ↓
commit
```

For the current one-invoice payment model:

```text
0 payment       → pending
partial payment → partial
full payment    → paid
overpayment     → rejected
```

No silent overpayment is allowed during Phase 3.2.

---

## 5. Transaction Boundary

Every financial mutation must execute inside a transaction.

For payment recording:

```text
BEGIN
  ↓
SELECT invoice FOR UPDATE
  ↓
validate workspace relationship
  ↓
validate payment amount/date/method
  ↓
create payment
  ↓
recalculate invoice state
  ↓
COMMIT
```

The invoice lock is mandatory whenever its mutable financial balance is being changed.

Future allocation operations must lock all affected invoices/payments/credits in deterministic order where multiple records are involved.

---

## 6. Financial State Authority

The canonical service owns:

- Payment acceptance/rejection
- Invoice paid amount transition
- Invoice status transition
- Financial transaction sequencing

The following must not independently own those transitions:

- API views
- Serializers
- Background jobs
- Webhook handlers
- Dashboard code
- Model `save()` implementations
- Payment signals

External entry points delegate to the canonical service.

---

## 7. Invoice `paid_amount` and `status`

During the migration period, existing fields remain for compatibility.

Target authority:

```text
Canonical Financial Service
          ↓
Invoice.paid_amount
Invoice.status
```

The source of payment truth is the payment/allocation records, not arbitrary caller-supplied values.

No API may accept client-provided `paid_amount` or `status` as authoritative financial input.

---

## 8. Model `save()` Policy

The current `Invoice.save()` performs financial reconciliation from Payment rows. This is protected temporarily for backward compatibility but is not the long-term architecture.

Target:

```text
Invoice.save()
    ↓
structural persistence + validation
```

rather than:

```text
Invoice.save()
    ↓
financial state machine
```

Migration must be staged so existing tests and integrations remain green at every checkpoint.

---

## 9. Signal Policy

Payment `post_save` and `post_delete` currently recalculate Invoice state.

Target policy:

- Financial state transitions must not depend on signals.
- Signals must not duplicate canonical service work.
- If compatibility signals are temporarily retained, they must be deliberately scoped and proven non-conflicting.
- Eventually financial reconciliation signals are removed or reduced to non-authoritative side effects.

Signal registration must be deterministic through the application configuration.

---

## 10. Service Input Contract

The canonical payment operation should receive normalized domain data, conceptually:

```text
workspace
actor/user
invoice reference
amount
payment method
payment date
reference id
notes
```

The service, not the caller, determines:

- Workspace validity
- Invoice existence
- Current outstanding amount
- Allowed transition
- Resulting invoice state

---

## 11. Validation Layers

Validation must be layered.

### Serializer/API validation

Syntax and request-shape validation:

- Required fields
- Decimal parsing
- Date parsing
- Choice values
- Basic positive amount

### Service validation

Business rules:

- Workspace ownership
- Invoice state
- Outstanding balance
- Financial transition validity
- Permission/context assumptions

### Model/database validation

Invariant protection:

- Positive payment amount
- Non-negative invoice amounts
- Paid amount constraints
- Foreign-key integrity

No single layer should be expected to provide all protection.

---

## 12. Idempotency Direction

Phase 3.2 does not yet implement gateway webhook idempotency, but the canonical service must be designed to accept an eventual idempotency key/reference.

Future command shape:

```text
record_payment(..., idempotency_key=...)
```

Repeated delivery of the same financial event must not create duplicate money movements.

A future unique idempotency constraint should be workspace-aware where appropriate.

---

## 13. Audit Event Direction

Phase 3.2 does not require a complete audit-log system yet.

However, every canonical financial mutation must have a clear event boundary so future audit records can capture:

- Actor
- Workspace
- Operation
- Object/reference
- Amount
- Previous state
- New state
- Timestamp
- Idempotency/reference key

Financial records themselves remain the source of historical financial facts; audit events explain who/why/when a mutation occurred.

---

## 14. Read vs Write Separation

Financial reads may continue to use dedicated query/read services.

```text
WRITE
API → Canonical Financial Service → DB

READ
API → Financial Read Service → DB
```

Dashboard and settlement reporting must not mutate financial state.

Read models may be optimized later without changing financial write semantics.

---

## 15. Workspace Isolation

Every canonical operation requires an explicit workspace context.

The service must scope all lookup and mutation queries to that workspace where the domain relation permits it.

RLS remains defense-in-depth.

The service must remain correct even when application-level workspace authorization is the primary protection.

---

## 16. Concurrency Rules

For one invoice:

```text
Payment A ─┐
           ├→ serialized by invoice row lock
Payment B ─┘
```

The service must never calculate outstanding balance before acquiring the invoice lock.

Example:

```text
Invoice = ₹10,000

A requests ₹7,000
B requests ₹5,000
```

Correct outcome:

```text
A succeeds: ₹7,000
B sees remaining ₹3,000 and is rejected
```

The system must never produce ₹12,000 of accepted payment against a ₹10,000 invoice under concurrent requests.

---

## 17. Settlement Boundary

`calculate_final_settlement()` remains a read/calculation operation in Phase 3.2.

It may lock relevant rows when necessary for a consistent calculation, but it does not close or mutate the settlement lifecycle.

Future explicit settlement operations will be added separately.

---

## 18. Dashboard Boundary

Dashboard financial values remain read-only.

Current dashboard calculations are allowed to continue during Phase 3.2.

Once payment allocation/credits/adjustments exist, dashboard financial values must migrate to canonical financial read services so they no longer assume `Payment.amount == invoice settlement`.

---

## 19. Migration Sequence

Implementation must proceed incrementally:

```text
1. Add canonical service module/boundary
        ↓
2. Move current payment transition into service
        ↓
3. Add regression tests around service contract
        ↓
4. Route API payment creation through service
        ↓
5. Prove direct/model/signal behavior
        ↓
6. Remove competing financial state mutation
        ↓
7. Route future allocation/credit features through same boundary
```

No PaymentAllocation model should be introduced until this boundary is stable.

---

## 20. Compatibility Rule

During migration, old public service names may remain as compatibility wrappers if needed.

Example:

```text
create_payment(...)
        ↓
record_payment(...)
```

The wrapper must delegate to the canonical implementation rather than duplicate it.

This allows existing callers/tests to migrate without a breaking API change.

---

## 21. Testing Contract

Phase 3.2 tests must prove:

### Existing behavior

- Partial payment
- Full payment
- Overpayment rejection
- Zero/negative rejection
- Workspace isolation
- Invoice state updates
- Settlement calculation

### Canonical ownership

- API delegates to service
- Service owns invoice transition
- Caller cannot forge paid/status values
- Competing paths do not produce contradictory state

### Concurrency

- Concurrent payments cannot over-allocate an invoice

### Regression

- Existing dashboard financial totals remain unchanged for existing data
- Existing API response contracts remain compatible

---

## 22. Explicit Non-Goals

Do not implement in Phase 3.2:

- PaymentAllocation model
- Advance credit model
- Gateway integration
- Webhook processing
- Recurring billing scheduler
- Full ledger
- Refund lifecycle
- Complete settlement entity

Those depend on the canonical transition boundary established here.

---

## 23. Exit Criteria

Phase 3.2 is complete only when:

1. A single canonical financial service owns payment state transitions.
2. Existing payment behavior remains green.
3. Invoice state is not independently mutated by API logic.
4. Competing signal behavior is removed or made non-authoritative.
5. Payment mutations remain transactional and lock the invoice before balance calculation.
6. Workspace isolation remains enforced.
7. Existing settlement behavior remains intact.
8. Existing dashboard financial results remain intact.
9. Regression and concurrency tests are green.
10. CI is green.

---

## 24. Lock

This document is the **Phase 3.2 canonical financial service implementation source of truth**.

Any implementation proposal that conflicts with this document must be explicitly reviewed before coding.

**Status: LOCKED 🔒**
