# AjnihaStay — Phase 3 Financial Architecture

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-06  
**Branch:** `phase-1/workspace-multitenancy`

## Purpose

This document is the implementation architecture for Phase 3 of AjnihaStay. It translates the locked Market/Product Blueprint v2 and its Gap Audit into a controlled financial-lifecycle implementation plan.

Phase 3 extends the existing financial foundation. It does **not** replace the existing Charge → Invoice → Payment flow or regress existing billing behavior.

---

## 1. Non-Negotiable Preservation

The following existing capabilities are protected:

- Advance billing
- Arrears billing
- Monthly and daily billing cycles
- Partial payments
- Existing Charge → Invoice → Payment lifecycle
- Security deposit support
- Existing settlement calculation foundation
- Workspace isolation / RBAC / RLS
- Existing API/domain contracts unless a versioned breaking change is explicitly approved

Future financial work must preserve these semantics.

---

## 2. Financial Domain Direction

The target lifecycle is:

```text
Occupancy
    ↓
Charge / Billing Event
    ↓
Invoice
    ↓
Payment Allocation
    ↓
Financial State
    ↓
Settlement / Ledger / Reporting
```

The system must distinguish between:

- A **billing rule/event** that creates an amount due
- An **invoice** that represents a receivable
- A **payment** representing money received
- A **payment allocation** describing which receivable the money settles
- An **advance credit** representing money received before a receivable exists or beyond the amount allocated to it
- A **ledger entry** representing the accounting record of a financial event
- A **settlement** representing final financial closure for an occupancy/lease relationship

---

## 3. Canonical Financial State Authority

Financial state must have one canonical transition authority.

Long-term direction:

```text
Business Event
      ↓
Canonical Financial Service
      ↓
Validated State Transition
      ↓
Financial Records
      ↓
Ledger / Reporting / Notifications
```

### Rule

`Model.save()`, signals and API code must not become competing sources of financial truth.

Existing behavior is preserved while this consolidation is introduced incrementally.

Signals, where retained for compatibility, must not create contradictory state transitions.

---

## 4. Invoice State Machine

The invoice lifecycle must be explicit.

Minimum states:

```text
PENDING
   ↓
PARTIAL
   ↓
PAID
```

Additional future states may include:

- VOID
- CANCELLED
- WRITTEN_OFF

Rules:

- `PENDING`: no allocated payment
- `PARTIAL`: allocated payment is greater than zero but less than receivable amount
- `PAID`: allocated payment fully settles the receivable
- A void/cancelled invoice must not accept normal payment allocation
- A written-off balance must not remain falsely collectible

Existing pending/partial/paid behavior is protected.

---

## 5. Payment Model Direction

A payment represents money received.

A payment must not be forced to equal one invoice amount.

Target architecture:

```text
Payment
   ├── Allocation → Invoice A
   ├── Allocation → Invoice B
   └── Unallocated amount → Advance Credit
```

This enables:

- Partial payments
- One payment settling multiple invoices
- Advance payments
- Overpayment converted to advance credit
- Future invoice application
- Reconciliation

The existing single-invoice payment path remains supported during migration.

---

## 6. Payment Allocation

A dedicated allocation concept is the target design.

Conceptually:

```text
Payment
   ↓
PaymentAllocation
   ↓
Invoice
```

An allocation must contain at minimum:

- Payment reference
- Invoice reference
- Allocated amount
- Allocation timestamp
- Workspace context through the related financial records

Rules:

1. Allocation amount must be positive.
2. Total allocations cannot exceed payment amount.
3. Total allocations against an invoice cannot exceed its collectible balance unless an explicitly defined credit/adjustment mechanism applies.
4. Allocation must be transactional.
5. Invoice state is derived from allocated receivable settlement.
6. Cross-workspace allocation is forbidden.
7. Duplicate webhook/retry processing must be idempotent at the integration boundary.

---

## 7. Advance Payment / Prepaid Credit

The product must distinguish **advance billing** from **advance money received**.

### Advance billing

Existing occupancy setting:

```text
billing_type = advance
```

means the billing period is billed before/at the start of service.

### Advance payment

Advance payment means money received before a corresponding receivable exists, or money remaining after an invoice is fully allocated.

Target flow:

```text
Payment ₹30,000
        ↓
Invoice ₹20,000
        ↓
Allocate ₹20,000
        ↓
Advance Credit ₹10,000
```

Later:

```text
New Invoice ₹20,000
        ↓
Apply Advance Credit ₹10,000
        ↓
Outstanding ₹10,000
```

Advance credits must be auditable, workspace-safe and explicitly allocated/consumed. They must not be silently hidden inside invoice `paid_amount`.

---

## 8. Arrears Billing

Arrears billing remains protected.

The recurring billing engine must support:

```text
Occupancy period
      ↓
Period closes / becomes billable
      ↓
Charge generation
      ↓
Invoice
```

No Phase 3 design may assume all rent is advance-billed.

---

## 9. Recurring Billing Engine

Recurring billing is a rules engine, not simply a scheduled database insert.

Target concepts:

- Billing schedule
- Billing frequency
- Billing type
- Effective start/end dates
- Charge category
- Amount/rate
- Proration policy
- Generation policy
- Idempotency key/reference

Supported strategic frequencies:

- Daily
- Weekly where required
- Monthly
- Future configurable frequencies

The first implementation should prioritize existing daily/monthly semantics.

---

## 10. Charge Engine

Current Charge remains a financial primitive.

Future Charge Engine responsibilities:

```text
Billing Rule
    ↓
Charge Event
    ↓
Charge
```

It must support future categories such as:

- Rent
- Electricity
- Food
- Maintenance
- Laundry
- Utilities
- Service charges
- Custom charges

Future extensions:

- Metered charges
- Fixed recurring charges
- Usage-based charges
- Discounts
- Credits
- Adjustments
- Taxes
- Late fees
- Proration

Existing charge validation and supported charge types must not regress.

---

## 11. Invoice Generation

Invoice generation must be deterministic and idempotent.

For a given billing event, the system must not create duplicate invoices when the operation is retried.

Invoice generation must define:

- Billing period
- Rent amount
- Charge amount
- Adjustments
- Credits
- Total receivable
- Due date
- Source billing event/rule

Future implementation should prefer explicit invoice line-item semantics rather than embedding every financial concept into aggregate amount fields.

---

## 12. Partial Payments

Partial payments are protected and remain first-class.

Example:

```text
Invoice ₹20,000

Payment ₹8,000 → PARTIAL
Payment ₹7,000 → PARTIAL
Payment ₹5,000 → PAID
```

Payment allocation must preserve this behavior.

No migration may reinterpret partial payment as an invalid or exceptional case.

---

## 13. Credits, Debits and Adjustments

Future financial adjustments must be explicit.

Supported concepts should eventually include:

- Credit adjustment
- Debit adjustment
- Discount
- Waiver
- Write-off
- Refund

Adjustments must be auditable and must not mutate historical payment records to achieve a new balance.

---

## 14. Late Fees

Late fees should be generated by explicit policy/rule, not by arbitrary code inside invoice save methods.

Possible policies:

- Fixed fee
- Percentage
- Per-day fee
- Grace period
- Maximum cap

Late fee generation must be idempotent.

---

## 15. Security Deposit

Existing security deposit support is preserved.

The long-term model must distinguish:

- Deposit required
- Deposit received
- Deposit held
- Deposit applied
- Deposit refunded
- Deposit forfeited/adjusted where legally/business appropriate

Deposit money must not be silently treated as rent income.

---

## 16. Settlement Lifecycle

Existing final-settlement calculation is preserved as the foundation.

Target lifecycle:

```text
Occupancy / Lease Ending
        ↓
Calculate Final Position
        ↓
Outstanding / Credits / Deposit
        ↓
Adjustments
        ↓
Refund / Collection
        ↓
Settlement Closed
```

Settlement must eventually become an explicit lifecycle/entity rather than only a calculation response.

---

## 17. Ledger Foundation

Ledger is a downstream financial record, not a replacement for operational invoices/payments.

Target direction:

```text
Financial Event
      ↓
Canonical Service
      ↓
Operational Financial Record
      ↓
Ledger Entry
```

Ledger implementation must support auditability and immutable historical meaning.

The first ledger phase should establish foundations rather than attempt a complete enterprise accounting suite.

---

## 18. Reconciliation & Gateway Readiness

Payment gateway integrations will eventually produce:

```text
Payment Intent
   ↓
Gateway Transaction
   ↓
Webhook
   ↓
Verified Payment
   ↓
Allocation
   ↓
Settlement
   ↓
Reconciliation
```

Webhook processing must be:

- Idempotent
- Authenticated/verified
- Workspace-safe
- Retry-safe
- Auditable

Gateway settlement must remain distinct from customer invoice settlement.

---

## 19. Transaction & Concurrency Rules

Financial mutations must be transactional.

For invoice/payment operations:

- Lock the relevant financial record before calculating mutable balance.
- Validate against current database state.
- Create allocation/state changes atomically.
- Never allow concurrent operations to over-allocate an invoice or advance credit.
- Retry-safe integrations must not duplicate financial effects.

Existing `select_for_update()` protections are preserved and extended where necessary.

---

## 20. Workspace Isolation

Every financial object must remain workspace-isolated.

No payment, allocation, invoice, charge, credit, settlement or ledger entry may cross workspace boundaries.

RLS remains defense-in-depth; application-level authorization remains mandatory.

---

## 21. Financial Invariants

The implementation must preserve these invariants:

```text
Allocated Payment ≤ Payment Amount

Invoice Allocated Amount ≤ Collectible Invoice Amount

Outstanding = Receivable - Valid Allocations - Explicit Credits/Adjustments

Paid Invoice ⇒ Outstanding = 0

Negative financial amounts are forbidden unless the specific domain object explicitly represents a credit/refund/adjustment.

Cross-workspace financial relationships are forbidden.
```

Exact accounting equations may be refined when the ledger model is introduced, but historical financial records must remain explainable.

---

## 22. Implementation Order

Phase 3 implementation follows this order:

```text
3.1 Financial architecture / state audit
        ↓
3.2 Canonical financial transition service
        ↓
3.3 Remove competing financial state mutation
        ↓
3.4 Charge engine foundation
        ↓
3.5 Recurring billing foundation
        ↓
3.6 Deterministic invoice generation
        ↓
3.7 Payment allocation
        ↓
3.8 Advance credit / prepaid balance
        ↓
3.9 Credits / debits / adjustments
        ↓
3.10 Late-fee foundation
        ↓
3.11 Settlement lifecycle
        ↓
3.12 Ledger foundation
        ↓
3.13 Financial reporting expansion
```

Each step must be implemented as:

`Architecture → Models → Service → API → Tests → Real integration → CI green`

---

## 23. Migration Strategy

Existing financial records must remain valid.

Migration requirements:

- No destructive financial migration without explicit approval.
- Existing invoice/payment balances must remain explainable.
- Existing partial-payment states must map correctly.
- Existing advance/arrears billing semantics must remain intact.
- Any new allocation/credit records introduced for historical data must be deterministic and auditable.
- Backfill must be tested before production execution.

---

## 24. API Compatibility

Existing APIs remain protected unless a versioned contract change is explicitly approved.

New capabilities should prefer additive endpoints/fields where possible.

Financial APIs must expose clear state and error semantics and must not rely on frontend calculations for financial truth.

---

## 25. Testing Requirements

Every financial phase must include:

### Domain tests
- State transitions
- Amount validation
- Billing periods
- Advance/arrears behavior
- Partial payments
- Credits/adjustments

### Concurrency tests
- Concurrent payment allocation
- Duplicate webhook/retry
- Over-allocation prevention
- Advance-credit race conditions

### Workspace tests
- Cross-workspace read blocking
- Cross-workspace mutation blocking
- Cross-workspace allocation rejection

### Regression tests
- Existing Charge → Invoice → Payment flow
- Existing partial payments
- Existing advance billing
- Existing arrears billing
- Security deposits
- Settlement calculation
- Dashboard financial totals

### Integration tests
- Real PostgreSQL
- RLS where enabled
- Migration graph
- Full Django suite

---

## 26. Explicit Non-Goals for Initial Phase 3

Do not attempt to build all of the following at once:

- Full ERP accounting
- Full enterprise general ledger
- Every payment gateway
- Every tax jurisdiction
- Full AI financial automation
- Complex commercial CAM/NNN accounting before core lifecycle is stable

Phase 3 establishes the financial core that later modules can safely depend upon.

---

## 27. Architecture Decision Summary

### KEEP 🔒

- Charge
- Invoice
- Payment
- Partial payments
- Advance billing
- Arrears billing
- Security deposit
- Existing settlement calculation

### EXTEND ➕

- Payment allocation
- Advance credit
- Recurring billing
- Charge rules
- Invoice generation
- Adjustments
- Late fees
- Settlement lifecycle
- Ledger
- Reconciliation

### REFACTOR CAREFULLY 🔧

- Financial state mutation currently distributed across model save, signals and services

### DO NOT REWRITE ❌

- Property hierarchy
- Occupancy architecture
- Workspace/RBAC/RLS architecture
- Existing validated financial workflows

---

## 28. Phase 3 Exit Criteria

Phase 3 is complete only when:

1. Financial state has one canonical transition authority.
2. Existing partial payments continue to work.
3. Advance billing continues to work.
4. Arrears billing continues to work.
5. Recurring billing is deterministic and idempotent.
6. Payment allocation is transactional and concurrency-safe.
7. Advance credits are explicit and auditable.
8. Settlement has an explicit lifecycle foundation.
9. Ledger foundation exists without corrupting operational records.
10. Workspace isolation is proven for all new financial objects.
11. Regression suite is green.
12. CI is green.
13. No UI changes are required to declare the backend financial foundation complete.

---

## 29. Lock

This document is the **Phase 3 financial implementation source of truth**.

Any implementation proposal that conflicts with this document must be explicitly reviewed and approved before coding.

**Status: LOCKED 🔒**
