# AjnihaStay — Phase 3.8 Advance Credit / Prepaid Balance

**Status:** LOCKED 🔒  
**Version:** v1.0  
**Date:** 2026-09-07  
**Branch:** `phase-1/workspace-multitenancy`

## 1. Purpose

Phase 3.8 introduces an explicit, auditable **Advance Credit / Prepaid Balance** layer for money received that is not currently represented by an invoice receivable, or remains after invoice allocation.

This phase is an additive extension of the existing financial lifecycle:

```text
Occupancy
    ↓
Charge / Billing Event
    ↓
Invoice
    ↓
Payment
    ↓
PaymentAllocation
    ↓
Financial State
```

The new prepaid path becomes:

```text
Payment
    ↓
Unallocated Amount
    ↓
AdvanceCredit
    ↓
AdvanceCreditApplication
    ↓
Future Invoice
```

The phase must preserve existing partial payments, advance billing, arrears billing, invoice generation, payment allocation, settlement calculation, workspace isolation and RLS.

---

## 2. Audit Basis

This architecture was audited against the locked product and financial sources of truth:

- `docs/BLUEPRINT.md`
- `docs/BLUEPRINT_V2_GAP_AUDIT.md`
- `docs/PHASE_3_FINANCIAL_ARCHITECTURE.md`
- Existing Phase 3.3 Payment Allocation implementation
- Existing Phase 3.4 recurring billing / charge generation / invoice generation implementation
- Current `payments.Invoice`, `payments.Payment`, `payments.PaymentAllocation` models
- Current payment/allocation services and APIs
- Current `tenant.Tenant`, `tenant.Occupancy`, and `tenant.Charge` models
- Current financial settlement calculation
- Current PostgreSQL RLS protection for financial tables

The audit confirms that **advance billing is already supported and must not be confused with advance money received**. The missing domain capability is an explicit, auditable prepaid credit that can be consumed against a later receivable.

---

## 3. Current-State Audit Findings

### 3.1 Payment already supports an unlinked state

`Payment.invoice` is nullable. Therefore the existing schema can represent a payment that is not currently attached to an invoice.

This is useful foundation and must be preserved.

### 3.2 Payment allocation already provides canonical invoice settlement

`PaymentAllocation` is the canonical relationship used to determine invoice-paid state. Allocation is transactional, locks payment/invoices, validates workspace ownership and prevents allocation above payment capacity or invoice outstanding balance.

Phase 3.8 must extend this model rather than bypass it.

### 3.3 Payment has an unallocated amount concept

`Payment.unallocated_amount` currently represents payment amount minus persisted allocations.

Phase 3.8 must refine this concept so an amount reserved as explicit advance credit cannot be accidentally allocated again directly from the same payment.

### 3.4 Current payment creation deliberately rejects invoice overpayment

The canonical payment service currently validates the payment amount against the invoice outstanding amount. This behavior is protected.

Phase 3.8 must **not** weaken this validation merely to create prepaid credit.

Instead, advance money should be represented by an explicitly unlinked payment or by an explicitly converted unallocated residual amount.

### 3.5 Existing settlement already reads payment allocations

Final settlement calculation uses `PaymentAllocation` totals. Phase 3.8 must ensure prepaid credit is not silently counted as invoice payment before it is actually applied to an invoice.

### 3.6 Existing workspace isolation is strong

Invoice, Payment and PaymentAllocation are workspace protected at the application layer and through PostgreSQL RLS. The new credit objects must receive the same defense-in-depth treatment.

---

## 4. Terminology — LOCKED

### Advance billing

Existing `Occupancy.billing_type = "advance"` means the billing period is billed in advance/at the beginning of the service period.

**It is not a credit balance.**

### Advance payment / prepaid credit

Money has been received but is not currently settling a receivable.

Examples:

```text
Payment ₹30,000
Invoice allocation ₹20,000
Remaining ₹10,000
        ↓
Advance Credit ₹10,000
```

or:

```text
Payment ₹20,000
No current invoice
        ↓
Advance Credit ₹20,000
```

The credit is a real financial state and must be auditable.

---

## 5. Architectural Decision

### 5.1 New bounded financial objects

Phase 3.8 introduces two explicit concepts:

```text
AdvanceCredit
    ↓
AdvanceCreditApplication
    ↓
Invoice
```

`AdvanceCredit` represents the original prepaid balance.  
`AdvanceCreditApplication` represents consumption of that balance against a specific invoice.

This avoids storing prepaid money inside `Invoice.paid_amount` or silently mutating historical `Payment` records.

### 5.2 Credit ownership

The credit is **tenant-scoped** and optionally occupancy-associated.

Rationale:

- The money belongs to the tenant/customer relationship, not to a specific invoice.
- A tenant may have a future occupancy/invoice.
- Historical occupancy can end while valid prepaid money remains.
- Tenant scope avoids forcing future credit to remain tied to one invoice.
- Optional occupancy context preserves traceability when the credit originated from a specific occupancy.

Workspace remains mandatory.

### 5.3 Source payment is mandatory

Every AdvanceCredit must reference the Payment from which the prepaid amount originated.

No anonymous/manual credit balance is created in Phase 3.8.

This gives an auditable chain:

```text
Payment → AdvanceCredit → AdvanceCreditApplication → Invoice
```

Manual accounting adjustments/credits belong to the later Credits/Debits/Adjustments phase.

---

## 6. Proposed Data Model

### 6.1 `AdvanceCredit`

Proposed fields:

```text
id
workspace FK → Workspace
tenant FK → Tenant
occupancy FK → Occupancy, nullable
source_payment OneToOne/unique FK → Payment
original_amount Decimal(10,2)
created_at
```

Constraints/invariants:

- `original_amount > 0`
- workspace is required
- source payment is required
- source payment must belong to the same workspace
- tenant must belong to the same workspace
- optional occupancy must belong to the same tenant/workspace
- source payment must not be reused to create multiple credit principals
- credit principal is immutable after creation

The remaining/available balance is **derived**, not stored as a second mutable financial truth:

```text
available_credit = original_amount - SUM(valid AdvanceCreditApplication.amount)
```

### 6.2 `AdvanceCreditApplication`

Proposed fields:

```text
id
credit FK → AdvanceCredit
invoice FK → Invoice
amount Decimal(10,2)
created_at
```

Constraints/invariants:

- `amount > 0`
- credit and invoice must belong to the same workspace
- invoice tenant must match credit tenant
- invoice occupancy must belong to the credit tenant
- total applications cannot exceed available credit
- one application cannot exceed invoice outstanding amount
- application records are immutable after creation
- applications are created transactionally

Recommended indexes:

```text
(credit)
(invoice)
(credit, created_at)
```

Recommended database constraint:

```text
advance_credit_application_amount_positive
```

A database constraint cannot by itself enforce aggregate credit capacity; that invariant remains under the canonical transactional service with row locks.

---

## 7. Payment Integration Rules

### 7.1 Explicit conversion only

Phase 3.8 must not automatically convert every unallocated payment into credit merely because `Payment.invoice` is null.

Credit creation must be an explicit domain transition.

This prevents ambiguous or incorrectly attributed payments from becoming prepaid balances.

### 7.2 Residual conversion

For a payment with existing allocations:

```text
Payment amount
    - existing allocations
    = unallocated amount
```

Only the unallocated amount may be converted into AdvanceCredit.

The service must lock the Payment before calculating this amount.

### 7.3 Full advance payment

For an unlinked payment:

```text
Payment amount = available prepaid amount
```

The caller must provide/resolve the tenant and optional occupancy context for the credit.

### 7.4 No double spending

Once an unallocated amount is reserved as an AdvanceCredit, the same amount must not remain directly allocatable through `PaymentAllocation`.

Therefore the canonical allocation capacity becomes conceptually:

```text
Payment allocatable amount
    = payment amount
    - existing invoice allocations
    - amount reserved into AdvanceCredit
```

The existing `Payment.unallocated_amount` read-side semantics must be updated accordingly during implementation.

### 7.5 Credit application does not create another Payment

Applying a prepaid credit to an invoice is a transfer of already-received money into invoice settlement.

It must create an `AdvanceCreditApplication` and update invoice financial state through the canonical financial transition authority.

It must not create a duplicate Payment.

---

## 8. Canonical Services

Phase 3.8 must use service-layer financial transitions.

### 8.1 `create_advance_credit(...)`

Responsibilities:

1. Resolve and workspace-scope Payment.
2. Lock Payment with `select_for_update()`.
3. Resolve tenant and optional occupancy.
4. Validate tenant/workspace ownership.
5. Calculate current allocatable/unallocated payment balance.
6. Reject zero/negative conversion.
7. Prevent duplicate credit principal for the same source payment.
8. Create immutable AdvanceCredit atomically.
9. Return the credit with derived available balance.

No invoice state is changed by credit creation.

### 8.2 `apply_advance_credit(...)`

Responsibilities:

1. Lock AdvanceCredit.
2. Lock target Invoice deterministically.
3. Validate same workspace.
4. Validate same tenant.
5. Calculate current available credit from applications.
6. Calculate current invoice outstanding from PaymentAllocation and existing financial state.
7. Reject application above either balance.
8. Create immutable AdvanceCreditApplication atomically.
9. Transition invoice state through the canonical financial service.
10. Return the application and updated financial state.

Concurrency rule:

```text
Lock Credit → Lock Invoice → Recalculate → Validate → Apply
```

Lock ordering must be deterministic for multi-object operations.

---

## 9. Invoice State Rules

Advance credit must not change an invoice until it is explicitly applied.

Before application:

```text
Invoice ₹20,000
Payment allocations ₹0
Advance credit ₹10,000

Invoice outstanding = ₹20,000
Credit available = ₹10,000
```

After application:

```text
Invoice ₹20,000
Credit application ₹10,000

Invoice outstanding = ₹10,000
Credit available = ₹0
```

Invoice `paid_amount/status` remains derived from valid settlement records and must not be manually mutated by the API.

The existing pending/partial/paid semantics remain protected.

---

## 10. Settlement Rules

Advance credit is a customer credit, not an invoice payment until applied.

Therefore:

- It must not reduce invoice outstanding before application.
- It must not be counted as collected against an invoice before application.
- It must not silently become security-deposit income.
- It must remain visible as available tenant credit.
- Future settlement logic must account for unapplied credit separately from invoice receivables.

The current settlement calculation must remain backward compatible. Phase 3.8 may add explicit credit information only through an additive read-side extension; it must not reinterpret existing totals without explicit approval.

---

## 11. API Contract

Phase 3.8 should use additive, manager-authorized endpoints.

Proposed endpoints:

```text
POST /api/advance-credits/
GET  /api/advance-credits/
GET  /api/advance-credits/<credit_id>/
POST /api/advance-credits/<credit_id>/apply/
```

### Create request

Conceptually:

```json
{
  "payment": 123,
  "tenant": 45,
  "occupancy": 67
}
```

`occupancy` is optional only when business context genuinely spans future occupancy; tenant is mandatory for attribution.

### Apply request

```json
{
  "invoice": 456,
  "amount": "10000.00"
}
```

Responses must expose:

- credit id
- source payment
- tenant
- optional occupancy
- original amount
- available amount
- applications
- timestamps

Financial amounts must come from backend/domain calculations, never frontend arithmetic.

Public/tenant-facing credit mutation APIs are out of scope for this phase.

---

## 12. Permissions

Mutation endpoints require `WorkspaceManagerPermission`.

Read endpoints require `WorkspaceStaffPermission`.

All service calls must independently enforce workspace scope; permissions are not a substitute for domain isolation.

---

## 13. Workspace Isolation / RLS

New tables must be protected by PostgreSQL RLS.

Required protections:

```text
payments_advancecredit
payments_advancecreditapplication
```

RLS must ensure:

- credit rows are visible only when the credit workspace matches `app.workspace_id`
- application rows are visible only through a credit/invoice relationship belonging to the current workspace
- cross-workspace inserts are rejected
- cross-workspace updates/inserts cannot bypass application authorization

The existing `enable_workspace_rls` command must include both new tables.

Application-level workspace filtering remains mandatory even with RLS.

---

## 14. Migration Strategy

Phase 3.8 requires additive schema migration only.

No destructive changes to historical Invoice, Payment or PaymentAllocation records are permitted.

The migration must:

1. Create `AdvanceCredit`.
2. Create `AdvanceCreditApplication`.
3. Add required indexes and positive-amount constraints.
4. Apply RLS policies.
5. Update the RLS enable/force command.
6. Preserve existing migration graph and all historical financial data.

Historical payments must **not** be automatically backfilled into AdvanceCredit during this phase unless a separately approved deterministic backfill design is created.

Reason: historical unallocated payments may lack sufficient tenant attribution and must not be guessed.

---

## 15. Model Mutation Rules

Financial truth must remain service-owned.

`AdvanceCredit.save()` and `AdvanceCreditApplication.save()` may validate structural invariants, but aggregate balances and financial transitions must not be implemented through model save side effects.

Persisted financial records are immutable after creation:

- source payment cannot change
- tenant cannot change
- occupancy cannot change
- principal amount cannot change
- application credit cannot change
- application invoice cannot change
- application amount cannot change

Corrections belong to later explicit adjustment/refund flows.

---

## 16. Testing Requirements

### Domain tests

- Positive credit amount only.
- Same-workspace payment/tenant/occupancy.
- Occupancy belongs to tenant.
- Duplicate source payment credit rejected.
- Full unlinked payment converted correctly.
- Residual payment amount converted correctly.
- Zero residual rejected.
- Credit balance derived from applications.
- Application cannot exceed available credit.
- Application cannot exceed invoice outstanding.
- Invoice state changes correctly after credit application.
- Credit creation does not change invoice state.
- Credit application does not create duplicate Payment.

### Concurrency tests

- Two concurrent credit applications cannot overspend the same credit.
- Two concurrent allocations cannot consume a payment amount reserved as credit.
- Credit application and payment allocation cannot over-settle an invoice.
- Duplicate retry cannot create duplicate credit principal.

### Workspace tests

- Cross-workspace credit creation rejected.
- Cross-workspace credit read blocked.
- Cross-workspace application rejected.
- Cross-workspace invoice/tenant relationships rejected.
- RLS blocks direct cross-workspace access.

### Regression tests

Must remain green:

- Existing payment creation.
- Partial payments.
- Advance billing.
- Arrears billing.
- Payment allocation.
- Recurring billing.
- Charge generation.
- Invoice generation.
- Dashboard financial totals.
- Final settlement calculation.

### Migration/integration tests

- `makemigrations --check --dry-run`
- migration graph validation
- migrations apply cleanly on PostgreSQL
- workspace RLS enable/force succeeds
- full Django test suite
- Django system checks
- CI GREEN

---

## 17. Explicit Non-Goals

Phase 3.8 does **not** implement:

- Generic credits/debits/adjustments.
- Credit notes/debit notes.
- Refunds.
- Credit expiry.
- Promotional/store credit.
- Interest/yield on prepaid balances.
- Automatic credit allocation policy engine.
- Gateway/webhook integration.
- UPI/payment links.
- Reconciliation.
- Ledger/GL accounting entries.
- Tax/GST treatment of credits.
- Historical automatic backfill.
- Tenant-facing credit mutation APIs.
- UI redesign.

These belong to later financial/integration phases unless explicitly pulled forward by a locked architecture change.

---

## 18. Implementation Order

Implementation must follow the project standard:

```text
1. Final model/FK/migration audit
        ↓
2. Lock architecture document
        ↓
3. Models + migrations
        ↓
4. Service/provider layer
        ↓
5. API + serializers
        ↓
6. Domain + concurrency + workspace tests
        ↓
7. Real PostgreSQL + RLS integration
        ↓
8. Full regression suite
        ↓
9. Migration/system-check verification
        ↓
10. CI GREEN
        ↓
11. Final architecture/security/financial audit
        ↓
12. Mark this document COMPLETE
```

No implementation should begin until this document is accepted as the Phase 3.8 source of truth.

---

## 19. Completion Gate

Phase 3.8 may be marked **COMPLETE** only when all of the following are true:

1. AdvanceCredit and AdvanceCreditApplication exist with correct workspace ownership.
2. Advance credit is explicitly distinguishable from advance billing.
3. Every credit has an auditable source Payment.
4. Unallocated/reserved payment capacity cannot be double-spent.
5. Credit balance is derived from immutable application records.
6. Credit application is transactional and concurrency-safe.
7. Invoice settlement is updated through the canonical financial transition authority.
8. Existing partial, advance and arrears workflows remain unchanged.
9. Existing PaymentAllocation behavior remains valid.
10. Settlement and dashboard totals do not falsely treat unapplied credit as invoice collection.
11. RLS protects both new tables.
12. Cross-workspace access/mutation is blocked.
13. Full regression tests are green.
14. Migration checks are green.
15. CI is GREEN on the final commit.
16. Final financial integrity audit passes.

---

## 20. Final Architecture Decision

### KEEP 🔒

- Existing Payment model and nullable invoice foundation.
- Existing PaymentAllocation as invoice-settlement primitive.
- Existing partial-payment behavior.
- Existing advance billing semantics.
- Existing arrears billing semantics.
- Existing invoice state machine.
- Existing workspace/RBAC/RLS architecture.
- Existing settlement calculation foundation.

### EXTEND ➕

- Explicit AdvanceCredit.
- Explicit AdvanceCreditApplication.
- Payment allocatable-capacity calculation to account for reserved credit.
- Canonical credit creation/application services.
- Additive staff/manager APIs.
- Financial read-side visibility for available prepaid balance.

### DO NOT REWRITE ❌

- Property hierarchy.
- Tenant/Occupancy architecture.
- Invoice architecture.
- PaymentAllocation architecture.
- Existing recurring billing architecture.
- Existing validated payment workflows.
- UI architecture.

### Golden Rule

> **Advance money received must be represented as an explicit, auditable credit and must never be silently hidden inside invoice payment state.**

**Status: LOCKED 🔒**
