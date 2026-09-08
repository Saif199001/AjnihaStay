# AjnihaStay — Phase 3.9 Credits / Debits / Financial Adjustments

**Status:** LOCKED 🔒  
**Version:** v1.1  
**Date:** 2026-09-08  
**Branch:** `phase-3.9-architecture-draft`

## 1. Purpose

Phase 3.9 introduces explicit, immutable and auditable financial adjustments without rewriting the protected Charge → Invoice → Payment lifecycle.

The phase covers receivable-side corrections:

- Credit adjustments
- Debit adjustments
- Discounts
- Waivers
- Controlled write-offs

Refunds, gateway settlement, reconciliation and ledger/GL remain separate future concerns.

## 2. Architecture Baseline

This architecture was reviewed against the locked product blueprint, locked Phase 3 Financial Architecture, Phase 3.8 Advance Credit architecture, and the current payment/advance-credit/allocation implementation.

Protected foundation:

```text
Occupancy → Charge → Invoice
                       ↓
                 PaymentAllocation
                       ↓
                 Invoice settlement

Payment → AdvanceCredit → AdvanceCreditApplication → Invoice settlement
```

Current settlement is already derived from immutable `PaymentAllocation` and `AdvanceCreditApplication` records. Phase 3.9 adds receivable-side adjustment events; it does not redefine money received or mutate historical financial events.

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
    = explicit reduction of collectible receivable
```

Therefore:

**Adjustment ≠ Payment**  
**Adjustment ≠ Refund**  
**Advance Credit ≠ Discount**  
**Write-off ≠ Payment**

## 5. Canonical Financial Equation

Phase 3.9 establishes the operational invoice-position equation:

```text
Gross Receivable
+ Debit Adjustments
- Credit Adjustments
= Adjusted Receivable

Settlement
= Payment Allocations
+ Advance Credit Applications

Outstanding
= max(Adjusted Receivable - Settlement, 0)
```

`discount`, `waiver`, and `write_off` are credit-side receivable adjustments but remain separately typed for reporting and future accounting.

### Boundary rule

A credit-side adjustment may not reduce adjusted receivable below already-recorded settlement. This prevents unexplained negative outstanding and prevents an adjustment from silently creating customer credit.

If a business event would require customer credit or money to be returned, that event is outside ordinary Phase 3.9 adjustment creation and must use a future explicit credit/refund mechanism.

## 6. Bounded Domain Model

Phase 3.9 introduces one immutable record:

```text
FinancialAdjustment
    id
    workspace FK → Workspace
    invoice FK → Invoice
    adjustment_type
    amount
    reason
    reference
    idempotency_key (nullable, unique within workspace)
    created_by FK → User
    created_at
```

Adjustment types:

```text
credit
 debit
 discount
 waiver
 write_off
```

Rules:

- `amount > 0` at database level.
- Direction is represented by `adjustment_type`; amount is never negative.
- Workspace must equal invoice workspace.
- Invoice ownership is validated server-side.
- `reason` is required for manual adjustments.
- `reference` is optional business/support evidence.
- `idempotency_key` is optional for backward-compatible domain usage but required for mutation API requests.
- Adjustment records are immutable after creation.
- Historical Payment, PaymentAllocation and AdvanceCredit records are never rewritten.
- `created_by` identifies the operator responsible for the event.

A separate table per adjustment type is not justified at this stage.

## 7. Adjustment Semantics

### Credit adjustment

Reduces collectible receivable.

```text
Invoice ₹20,000
Credit ₹2,000
Adjusted receivable = ₹18,000
```

### Debit adjustment

Increases collectible receivable.

```text
Invoice ₹20,000
Debit ₹2,000
Adjusted receivable = ₹22,000
```

### Discount

Commercial reduction of receivable. It is an explicit event and does not mutate `Invoice.rent_amount`, `charges_amount`, Charge records, or historical payments.

### Waiver

Operator-approved reduction of an otherwise collectible amount. It remains separately identifiable from a commercial discount.

### Write-off

Explicit reduction of collectible receivable because the amount is intentionally no longer collectible. In Phase 3.9 it is executable only through the canonical adjustment service and only with manager-level authorization. It remains distinguishable from discount/waiver for future accounting/reporting.

## 8. Canonical Invoice Financial Position

Phase 3.9 establishes one canonical read-side contract:

```text
calculate_invoice_financial_position(invoice)
```

It returns authoritative values conceptually equivalent to:

```text
{
    gross_receivable,
    debit_adjustments,
    credit_adjustments,
    adjusted_receivable,
    payment_allocations,
    advance_credit_applications,
    settled_amount,
    outstanding_amount,
    collection_closed,
    status,
}
```

The service must use `Decimal` values and derive them from current database records.

All payment allocation, advance-credit application and adjustment validation that depends on invoice outstanding must converge on this calculation. No API or frontend calculation is authoritative.

## 9. Invoice State and Existing Fields

`Invoice.paid_amount` remains a compatibility/read-side settlement field.

It continues to represent:

```text
paid_amount
    = PaymentAllocation
    + AdvanceCreditApplication
```

Adjustments never inflate or reduce historical paid/settled money.

The canonical financial service may update compatibility `paid_amount/status` as a derived state transition; `Model.save()`, signals and API code remain non-authoritative.

## 10. Paid / Partial / Pending Semantics

For backward compatibility, the existing `pending / partial / paid` states remain available.

For a positive adjusted receivable:

```text
settlement == adjusted receivable → PAID
0 < settlement < adjusted receivable → PARTIAL
settlement == 0 and adjusted receivable > 0 → PENDING
```

A credit/write-off may reduce adjusted receivable to zero only when it does not exceed recorded settlement. Therefore an unpaid invoice cannot be silently converted into `paid` by an adjustment.

If an adjustment closes the collectible balance at zero while settlement is zero, `collection_closed=True` is the authoritative financial-position signal. Existing `status` is retained as a compatibility field until a future explicit invoice lifecycle state (for example `written_off`) is introduced.

If settlement already equals the adjusted receivable, the invoice may remain `paid`; the adjustment does not rewrite historical payment data.

## 11. Guardrails

The canonical adjustment service rejects:

- Zero/negative/non-finite amounts
- Cross-workspace invoice
- Invalid adjustment type
- Missing required reason
- Mutation of an existing adjustment
- Unsupported invoice state
- Credit/discount/waiver/write-off exceeding the remaining collectible boundary
- Debit adjustments without required authorization
- Duplicate mutation API requests with the same idempotency key

Debit adjustments may increase receivable, subject to authorization and configured limits.

The service locks the invoice and calculates all mutable balances from current database state.

## 12. Canonical Adjustment Transition

The only authoritative mutation boundary is:

```text
Business Event
    ↓
Lock Invoice
    ↓
Validate workspace / authorization / state / type / amount
    ↓
Calculate current invoice financial position
    ↓
Validate adjusted-receivable boundary
    ↓
Create immutable FinancialAdjustment
    ↓
Recalculate compatibility invoice state
    ↓
Commit atomically
```

No financial adjustment is implemented through direct API-side balance mutation or model `save()` side effects.

## 13. Interaction with Payments

Adjustments do not alter Payment amount or PaymentAllocation history.

Example:

```text
Invoice ₹20,000
Payment ₹20,000
        ↓
PAID

Credit adjustment ₹5,000
```

The historical payment remains ₹20,000. The adjustment is recorded independently. Because settlement already equals the post-adjustment collectible amount, no negative outstanding is created.

A new credit-side adjustment that would require the system to return money is rejected by the ordinary adjustment boundary and deferred to a future refund/credit workflow.

## 14. Interaction with Advance Credit

Advance credit remains money already received and separate from receivable adjustments.

Example:

```text
Invoice ₹20,000
Advance Credit Application ₹5,000
Credit Adjustment ₹2,000

Adjusted receivable = ₹18,000
Settlement = ₹5,000
Outstanding = ₹13,000
```

An adjustment never changes `AdvanceCredit.original_amount`, `available_amount`, or historical applications.

Advance-credit application must use the same canonical invoice financial position for outstanding validation.

## 15. Interaction with Payment Allocation

Payment allocation remains governed by payment capacity and invoice outstanding.

Phase 3.9 requires allocation validation to reuse the canonical invoice-position calculation rather than maintaining a second outstanding equation.

This prevents inconsistent results such as:

```text
read-side outstanding = ₹8,000
allocation service outstanding = ₹10,000
```

Payment capacity rules remain unchanged, including reserved advance-credit capacity.

## 16. Concurrency

All adjustment mutations are transactional.

Required rules:

1. Lock the target invoice before calculating mutable receivable state.
2. Recalculate after the lock from current database state.
3. Create the adjustment and compatibility state transition atomically.
4. Concurrent credit-side adjustments cannot cross the collectible boundary.
5. Concurrent debit adjustments cannot lose updates.
6. Concurrent adjustment + payment allocation cannot over-settle the invoice.
7. Concurrent adjustment + advance-credit application cannot over-settle the invoice.
8. Multi-record lock ordering is deterministic.

Dedicated PostgreSQL adversarial tests are mandatory before Phase 3.9 completion.

## 17. Workspace / RBAC / RLS

Every adjustment is workspace-scoped through the invoice relationship and explicit workspace field.

Required protections:

- Manager-level mutation permission.
- Staff-level read permission.
- Service-level workspace validation independent of API permission checks.
- RLS enabled and forced for the new table.
- Cross-workspace direct access blocked.
- Cross-workspace related-object mutation blocked.
- `created_by` recorded for auditability.

Write-off uses the same manager-level mutation boundary; no separate weaker path is permitted.

## 18. API Contract Direction

Additive endpoints:

```text
POST /api/financial-adjustments/
GET  /api/financial-adjustments/
GET  /api/financial-adjustments/<id>/
```

Create request:

```json
{
  "invoice": 123,
  "adjustment_type": "credit",
  "amount": "2000.00",
  "reason": "Approved service issue credit",
  "reference": "CASE-123",
  "idempotency_key": "ADJ-CASE-123"
}
```

Contract rules:

- Mutation requires manager-level permission.
- Read requires staff-level permission.
- `idempotency_key` is required on create requests and is unique within workspace.
- Retry with the same key and semantically identical request returns the original adjustment/result rather than creating a duplicate.
- Reuse of a key with different business parameters is rejected.
- Backend returns authoritative adjustment data plus canonical invoice financial position.
- Exact public error strings will be frozen in the API implementation tests before release.

## 19. Idempotency Decision

The persisted `idempotency_key` is the Phase 3.9 manual mutation idempotency boundary.

Database uniqueness is scoped by workspace. The service must perform the idempotency lookup inside the same transaction as the adjustment creation and invoice lock.

Webhook/gateway idempotency remains outside this phase.

## 20. Auditability

Every adjustment must answer:

- Which workspace?
- Which invoice?
- What type?
- How much?
- Why?
- Who created it?
- When?
- What reference supports it?
- What idempotency key identified the mutation, when supplied by API?

A future generalized audit-log subsystem may add request/context metadata, but Phase 3.9 must not depend on it for preservation of the financial event.

## 21. Reporting Semantics

Reports must distinguish:

```text
Gross billed
Debit adjustments
Credit adjustments
Net collectible / adjusted receivable
Cash/payment settlement
Advance credit applied
Outstanding
Written off
```

A credit adjustment is not cash collection.

A write-off is not payment received.

An advance-credit application reduces invoice outstanding, while the original cash receipt remains attributable to its source Payment.

Discount and waiver remain separately reportable even though both reduce receivable.

## 22. Migration Strategy

Additive only.

Create the adjustment table with:

- workspace/invoice foreign keys
- positive amount constraint
- adjustment-type constraint/choices
- indexes for workspace/invoice/type/created_at as justified by query patterns
- idempotency uniqueness within workspace
- RLS enable/force and policies

No historical adjustment backfill is permitted without explicit business attribution.

No historical Payment or Invoice amount is rewritten merely to introduce the new model.

Required checks:

```text
makemigrations --check --dry-run
migration graph
migrate
RLS enable/force verification
```

## 23. Testing Requirements

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
- Fully settled invoice boundary.
- Credit-side adjustment cannot create negative outstanding.
- Payment records remain unchanged.
- `paid_amount` remains settlement-only.
- Zero collectible balance is not falsely reported as cash-paid.

### Idempotency

- Same API key returns original result.
- Same key with different payload is rejected.
- Concurrent duplicate requests create one adjustment.

### Concurrency

- Concurrent credit adjustments.
- Concurrent debit + payment allocation.
- Concurrent credit + advance-credit application.
- Boundary over-adjustment prevention.
- Deterministic multi-record locking.

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

## 24. Explicit Non-Goals

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
- Generalized audit-log subsystem

## 25. Implementation Order

```text
Architecture review + lock
        ↓
Model + migration
        ↓
Canonical invoice financial-position service
        ↓
Adjustment creation service
        ↓
Refactor payment allocation + advance-credit validation to canonical position
        ↓
API + serializer + idempotency
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

## 26. Round-2 Architecture Decisions — CLOSED

### Decision 1 — Post-settlement credit behavior

**LOCKED:** Ordinary Phase 3.9 credit/discount/waiver/write-off operations may not reduce adjusted receivable below already-recorded settlement.

No negative outstanding is created. A business event requiring customer credit or money return is deferred to the future explicit credit/refund workflow.

### Decision 2 — Manual API idempotency

**LOCKED:** `FinancialAdjustment.idempotency_key` is nullable at the domain level but required by mutation APIs, with workspace-scoped uniqueness and transactional duplicate detection.

### Decision 3 — Write-off scope

**LOCKED:** Write-off is executable in Phase 3.9, but only through the canonical adjustment service with manager-level authorization and full immutable/auditable event semantics. It does not introduce ledger accounting entries yet.

### Decision 4 — Canonical financial-position helper

**LOCKED:** `calculate_invoice_financial_position(invoice)` is the canonical invoice-position read contract. Payment allocation, advance-credit application, adjustment validation and later financial workflows must reuse it rather than duplicate outstanding calculations.

## 27. Review Findings Against Locked Architecture

### PASS

- Extends rather than rewrites Charge → Invoice → Payment.
- Preserves partial, advance and arrears semantics.
- Keeps Payment, PaymentAllocation and AdvanceCredit distinct from adjustments.
- Uses immutable financial events and canonical service transitions.
- Preserves workspace/RBAC/RLS requirements.
- Fits the locked Phase 3 sequence after Advance Credit.
- Keeps refunds, ledger and reconciliation outside this bounded phase.
- Resolves all four Round-1 open architecture decisions.
- Aligns invoice outstanding with one canonical financial-position contract.

### Current-code compatibility review

The current implementation already derives settlement from `PaymentAllocation + AdvanceCreditApplication`, reserves payment capacity for advance credit, locks invoice/payment records during financial transitions, and keeps adjustment-like historical records immutable. Phase 3.9 therefore extends the current architecture instead of replacing it.

The key implementation change is to introduce the canonical financial-position calculation and make existing allocation/advance-credit outstanding validation converge on it before exposing adjustment mutation broadly.

## 28. Architecture Lock Decision

**Status: LOCKED 🔒**

Round-2 architecture review is complete. All four previously open decisions are resolved and the document is now the Phase 3.9 implementation source of truth.

**No Phase 3.9 model/service/API implementation may intentionally deviate from this document without an explicit architecture review.**

## 29. Phase 3.9 Completion Gate

Phase 3.9 is complete only when:

1. Adjustments are explicit immutable financial records.
2. Credit/debit/discount/waiver/write-off semantics are distinguishable.
3. Invoice collectible balance has one canonical calculation.
4. `paid_amount` remains settlement-only and compatible.
5. Payment and advance-credit history is never mutated to represent an adjustment.
6. Payment allocation and advance-credit application use the canonical outstanding calculation.
7. Concurrency cannot over-adjust or over-settle an invoice.
8. Workspace/RBAC/RLS protections are proven.
9. API idempotency is proven under retry and concurrency.
10. Existing partial/advance/arrears/allocation/prepaid workflows remain green.
11. PostgreSQL migration/RLS checks are green.
12. CI is GREEN on the final implementation commit.
13. Final financial integrity audit passes.

**Golden Rule:**

> **Never mutate historical money or financial events to repair a balance; create an explicit, immutable, auditable financial event and let the canonical financial service derive the resulting state.**
