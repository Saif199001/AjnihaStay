# AjnihaStay — Phase 3.9 Credits / Debits / Financial Adjustments

**Status:** DRAFT — ARCHITECTURE REVIEWED 🔍  
**Version:** v1.0-draft  
**Date:** 2026-09-08  
**Branch:** `phase-3.9-architecture-draft`

## 1. Purpose

Phase 3.9 introduces explicit, immutable and auditable financial adjustments without rewriting the protected Charge → Invoice → Payment lifecycle.

The phase addresses receivable-side corrections such as:

- Credit adjustments
- Debit adjustments
- Discounts
- Waivers
- Controlled write-off foundation

Refunds, gateway settlement, reconciliation and ledger/GL remain separate future concerns.

## 2. Architecture Baseline

This draft was reviewed against the locked product blueprint, the locked Phase 3 Financial Architecture, the Phase 3.8 Advance Credit architecture, and the current payment/advance-credit/allocation implementation.

Protected foundation:

```text
Occupancy → Charge → Invoice
                       ↓
                 PaymentAllocation
                       ↓
                 Invoice settlement

Payment → AdvanceCredit → AdvanceCreditApplication → Invoice settlement
```

Current implementation already calculates invoice settlement as:

```text
SUM(PaymentAllocation.amount)
+ SUM(AdvanceCreditApplication.amount)
```

Phase 3.9 must extend the receivable calculation without redefining money received or mutating historical payments.

## 3. Non-Negotiable Preservation

The following remain protected:

- Workspace / RBAC / RLS
- Property → Unit → SubUnit
- Tenant / Occupancy semantics
- Advance billing
- Arrears billing
- Daily/monthly billing
- Partial payments
- Charge → Invoice → Payment
- PaymentAllocation
- AdvanceCredit / AdvanceCreditApplication
- Existing settlement calculation foundation
- Existing API/domain contracts unless explicitly versioned

No UI redesign is part of this phase.

## 4. Core Financial Distinctions

These concepts must never be collapsed into one generic balance mutation:

```text
Payment
    = money received

PaymentAllocation
    = payment applied to an invoice

AdvanceCredit
    = received money reserved for future use

Adjustment
    = explicit receivable-side correction

Refund
    = money returned from a payment

Write-off
    = explicit reduction of collectible receivable because it is no longer intended to be collected
```

In particular:

**Adjustment ≠ Payment**  
**Adjustment ≠ Refund**  
**Advance Credit ≠ Discount**  
**Write-off ≠ Payment**

## 5. Financial Equation

The canonical invoice position must evolve toward:

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

Discounts and waivers are represented as explicit credit-side adjustment events, not as mutation of historical payments.

Write-offs reduce collectible receivable through a separately identifiable adjustment type and must remain distinguishable for future accounting/reporting.

The exact ledger/accounting equation will be finalized when the ledger foundation is introduced.

## 6. Bounded Domain Model

### 6.1 FinancialAdjustment

Phase 3.9 proposes one bounded immutable adjustment record:

```text
FinancialAdjustment
    id
    workspace FK → Workspace
    invoice FK → Invoice
    adjustment_type
    amount
    reason
    reference
    created_by FK → User
    created_at
```

Recommended adjustment types:

```text
credit
 debit
 discount
 waiver
 write_off
```

Rules:

- `amount > 0` at the database level.
- Workspace must equal invoice workspace.
- Amount is never negative; direction is represented by `adjustment_type`.
- Invoice/reference ownership is validated server-side.
- Record is immutable after creation.
- Historical Payment, PaymentAllocation and AdvanceCredit records are never rewritten.
- `created_by` identifies the operator responsible for the business event.
- Reason is required for auditable manual corrections.

A separate table per adjustment type is not justified at this stage; these types share lifecycle, ownership, immutability and audit requirements.

## 7. Adjustment Semantics

### Credit adjustment

Reduces collectible receivable.

```text
Invoice ₹20,000
Credit ₹2,000
Outstanding before payment = ₹18,000
```

### Debit adjustment

Increases collectible receivable.

```text
Invoice ₹20,000
Debit ₹2,000
Outstanding = ₹22,000
```

### Discount

Commercial reduction of receivable. It remains an explicit event for reporting rather than changing `Invoice.rent_amount` or historical charge records.

### Waiver

Operator-approved reduction of an otherwise collectible amount. It remains separately identifiable from a commercial discount.

### Write-off

Reduction of collectible receivable because the amount is intentionally no longer collectible. It must remain distinguishable from discount/waiver for future accounting and reporting.

## 8. Invoice State and Existing Fields

`Invoice.paid_amount` remains a compatibility/read-side field maintained by the canonical financial service.

It must continue to represent **settlement**, not gross adjustment activity.

Therefore:

```text
paid_amount
    = PaymentAllocation
    + AdvanceCreditApplication
```

Adjustments change the receivable/outstanding calculation, not the historical money-received amount.

The existing `Invoice.save()` financial guards must not become a competing transition authority.

The canonical service will own recalculation of invoice financial position/status.

## 9. Paid / Partial / Pending Semantics

For the initial implementation, invoice status continues to be derived from settlement relative to the adjusted collectible receivable:

```text
settlement == collectible receivable → PAID
0 < settlement < collectible receivable → PARTIAL
settlement == 0 and collectible receivable > 0 → PENDING
```

A zero collectible balance caused entirely by a credit/write-off must not be misreported as customer cash collection.

Future explicit invoice lifecycle states such as VOID/CANCELLED may be introduced separately.

## 10. Guardrails

An adjustment service must reject:

- Zero/negative amounts
- Cross-workspace invoice
- Invalid adjustment type
- Missing required reason for manual adjustment
- Mutation of an existing adjustment
- Adjustment against an unsupported invoice state
- Credit/write-off that exceeds the remaining collectible balance
- Duplicate operation when an idempotency mechanism is supplied

Debit adjustments may increase the receivable, subject to configured limits and authorization policy.

The service must calculate all mutable balances from current database state while holding the relevant invoice lock.

## 11. Canonical Services

Phase 3.9 should introduce a dedicated service boundary, conceptually:

```text
create_financial_adjustment(...)
calculate_invoice_financial_position(invoice)
```

The creation workflow:

```text
Business Event
    ↓
Lock Invoice
    ↓
Validate workspace/state/type/amount
    ↓
Calculate current collectible balance
    ↓
Create immutable FinancialAdjustment
    ↓
Recalculate compatibility invoice state
    ↓
Commit atomically
```

No financial adjustment should be implemented through direct API-side mutation or model `save()` side effects.

## 12. Interaction with Payments

Adjustments do not alter Payment amount.

Example:

```text
Invoice ₹20,000
Payment ₹20,000
        ↓
PAID

Credit adjustment ₹5,000
        ↓
Historical payment remains ₹20,000
Financial position must remain explainable
```

The service must define the behavior of adjustments applied after settlement before implementation. The recommended rule is to prevent ordinary credit/write-off adjustments from creating an unexplained negative outstanding balance; any resulting customer credit should be represented by an explicit future credit/refund mechanism.

## 13. Interaction with Advance Credit

Advance credit is money already received and must remain separate.

Example:

```text
Invoice ₹20,000
Advance Credit Application ₹5,000
Credit Adjustment ₹2,000

Adjusted receivable = ₹18,000
Settlement = ₹5,000
Outstanding = ₹13,000
```

An adjustment must never increase or decrease `AdvanceCredit.available_amount` directly.

Credit applications remain immutable.

## 14. Interaction with Payment Allocation

Payment allocation continues to be governed by available payment capacity and adjusted invoice outstanding.

Therefore allocation validation must eventually use the same canonical invoice financial-position calculation introduced by Phase 3.9.

This prevents inconsistent behavior such as:

```text
read-side says outstanding ₹8,000
allocation service says outstanding ₹10,000
```

One canonical calculation must be reused by payment, advance-credit and adjustment workflows.

## 15. Concurrency

All financial adjustment mutations must be transactional.

Required rules:

1. Lock the target invoice before calculating mutable receivable state.
2. Recalculate from current database state after the lock.
3. Create the adjustment and compatibility state transition atomically.
4. Never allow concurrent adjustments to exceed allowed collectible boundaries.
5. Concurrent adjustment + payment allocation must not over-settle the invoice.
6. Concurrent adjustment + advance-credit application must not over-settle the invoice.
7. Lock ordering must remain deterministic wherever multiple financial records are involved.

Dedicated adversarial PostgreSQL concurrency tests are required before phase completion.

## 16. Workspace / RBAC / RLS

Every adjustment is workspace-scoped through the invoice/workspace relationship.

Required protections:

- Manager-level mutation permission.
- Staff-level read permission.
- Service-level workspace validation independent of API permission checks.
- RLS enabled and forced for the new table.
- Cross-workspace direct access blocked.
- Cross-workspace related-object mutation blocked.

The adjustment creator must be recorded for auditability.

## 17. API Direction

Additive endpoints are preferred:

```text
POST /api/financial-adjustments/
GET  /api/financial-adjustments/
GET  /api/financial-adjustments/<id>/
```

Possible create request:

```json
{
  "invoice": 123,
  "adjustment_type": "credit",
  "amount": "2000.00",
  "reason": "Approved service issue credit",
  "reference": "CASE-123"
}
```

Backend returns authoritative adjustment and invoice financial position.

Frontend must not calculate or persist financial truth.

Exact response fields and error strings will be locked during API implementation.

## 18. Idempotency

Manual adjustments require protection against accidental duplicate submission.

Phase 3.9 should define an optional client/reference idempotency key before exposing mutation APIs broadly.

The final persistence strategy must guarantee that retrying the same business operation does not create an unintended second adjustment.

Webhook idempotency remains outside this phase and belongs to gateway integration.

## 19. Auditability

Each adjustment must answer:

- Which workspace?
- Which invoice?
- What type?
- How much?
- Why?
- Who created it?
- When?
- What reference supports it?

A future generalized audit-log subsystem may record additional request/context metadata, but Phase 3.9 must not depend on that future subsystem to preserve the financial event itself.

## 20. Reporting Semantics

Reports must distinguish:

```text
Gross billed
Adjustments
Net collectible
Cash/payment settlement
Advance credit applied
Outstanding
Written off
```

A credit adjustment must not appear as cash collection.

A write-off must not appear as payment received.

An advance credit application may reduce invoice outstanding, but the original cash receipt remains attributable to the source Payment.

## 21. Migration Strategy

Additive only.

Create the adjustment table, indexes, positive amount constraint, workspace/RLS policies and required foreign keys.

No historical adjustment backfill is permitted without explicit business attribution.

No historical Payment or Invoice amounts may be rewritten merely to introduce the new model.

Required checks:

```text
makemigrations --check --dry-run
migration graph
migrate
RLS enable/force verification
```

## 22. Testing Requirements

### Domain

- Credit adjustment reduces collectible balance.
- Debit adjustment increases collectible balance.
- Discount remains distinguishable from generic credit.
- Waiver remains distinguishable from discount.
- Write-off remains distinguishable from discount/waiver.
- Positive amounts only.
- Invalid type rejected.
- Required reason enforced.
- Immutable adjustment records.
- Creator/workspace ownership validated.

### Financial interaction

- Partial payment + credit adjustment.
- Partial payment + debit adjustment.
- Advance credit application + adjustment.
- Allocation + adjustment.
- Fully settled invoice adjustment boundary.
- Adjustment cannot create unexplained negative outstanding.
- Payment records remain unchanged.

### Concurrency

- Concurrent credit adjustments.
- Concurrent debit + payment allocation.
- Concurrent credit + advance-credit application.
- Boundary over-adjustment prevention.
- Retry/idempotency behavior.

### Workspace/RLS

- Cross-workspace read blocked.
- Cross-workspace mutation blocked.
- Related invoice mismatch blocked.
- Direct RLS access blocked.

### Regression

- Existing partial payments.
- Advance billing.
- Arrears billing.
- Payment allocation.
- Advance credit.
- Recurring billing.
- Charge generation.
- Invoice generation.
- Dashboard totals.
- Final settlement calculation.

## 23. Explicit Non-Goals

Not implemented in Phase 3.9:

- Payment refunds
- Gateway/webhook integration
- Reconciliation
- Ledger/GL
- GST/tax engine
- Automatic late fees
- Credit expiry
- Promotional/store credit
- Automatic adjustment policy engine
- Historical automatic backfill
- UI redesign

These remain separate phases so the financial model stays bounded and auditable.

## 24. Implementation Order

```text
Architecture review + lock
        ↓
Model + migration
        ↓
Canonical invoice financial-position service
        ↓
Adjustment creation service
        ↓
API + serializer
        ↓
Domain tests
        ↓
Concurrency tests
        ↓
Workspace/RLS tests
        ↓
Regression suite
        ↓
PostgreSQL migration/system checks
        ↓
CI GREEN
        ↓
Final financial integrity audit
        ↓
Mark COMPLETE
```

## 25. Phase 3.9 Completion Gate

Phase 3.9 is complete only when:

1. Adjustments are explicit immutable financial records.
2. Credit/debit/discount/waiver/write-off semantics are distinguishable.
3. Invoice collectible balance has one canonical calculation.
4. `paid_amount` remains settlement-only and compatible.
5. Payment and advance-credit history is never mutated to represent an adjustment.
6. Payment allocation and advance-credit application use the canonical outstanding calculation.
7. Concurrency cannot over-adjust or over-settle an invoice.
8. Workspace/RBAC/RLS protections are proven.
9. Existing partial/advance/arrears/allocation/prepaid workflows remain green.
10. Regression suite is green.
11. PostgreSQL migration/RLS checks are green.
12. CI is GREEN on the final implementation commit.
13. Final financial integrity audit passes.

## 26. Review Findings Against Locked Architecture

### PASS

- Extends rather than rewrites the Charge → Invoice → Payment lifecycle.
- Preserves partial, advance and arrears semantics.
- Keeps Payment, PaymentAllocation and AdvanceCredit distinct from adjustments.
- Uses immutable financial events and canonical service transitions.
- Preserves workspace/RBAC/RLS requirements.
- Fits the locked Phase 3 sequence after Advance Credit.
- Keeps refunds, ledger and reconciliation outside this bounded phase.

### OPEN BEFORE IMPLEMENTATION

1. Finalize exact post-settlement credit-adjustment behavior. Recommendation: do not create negative outstanding; route resulting customer-credit/refund behavior to a later explicit credit/refund workflow.
2. Finalize idempotency key/reference persistence for manual API retries.
3. Finalize whether write-off is fully executable in 3.9 or only a typed adjustment foundation. Recommendation: executable but tightly permissioned, with future ledger semantics preserved.
4. Finalize canonical financial-position helper name and return contract before coding.

These are architecture decisions, not implementation details, and must be resolved before the document becomes LOCKED.

## 27. Architecture Lock Decision

**Current status: DRAFT — REVIEWED, NOT YET LOCKED.**

The draft is compatible with the locked product blueprint and Phase 3 financial architecture. No implementation should begin until the four open decisions above are resolved and this document is promoted to **Status: LOCKED**.

**Golden Rule:**

> **Never mutate historical money or financial events to repair a balance; create an explicit, immutable, auditable financial event and let the canonical financial service derive the resulting state.**
