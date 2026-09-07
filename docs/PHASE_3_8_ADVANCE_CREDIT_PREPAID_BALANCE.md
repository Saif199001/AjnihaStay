# AjnihaStay — Phase 3.8 Advance Credit / Prepaid Balance

**Status:** LOCKED 🔒  
**Version:** v1.1  
**Date:** 2026-09-07  
**Branch:** `phase-1/workspace-multitenancy`

## 1. Purpose

Phase 3.8 introduces an explicit, auditable **Advance Credit / Prepaid Balance** layer for money received that is not currently represented by an invoice receivable, or remains after invoice allocation.

This is additive to the protected lifecycle:

```text
Occupancy → Charge → Invoice → Payment → PaymentAllocation
```

The prepaid path is:

```text
Payment
   ↓
Unallocated / Reserved Amount
   ↓
AdvanceCredit
   ↓
AdvanceCreditApplication
   ↓
Invoice settlement
```

The phase must preserve partial payments, advance billing, arrears billing, recurring billing, invoice generation, payment allocation, settlement calculation, workspace isolation and RLS.

---

## 2. Audit Basis & Findings

Audited against:

- `docs/BLUEPRINT.md`
- `docs/BLUEPRINT_V2_GAP_AUDIT.md`
- `docs/PHASE_3_FINANCIAL_ARCHITECTURE.md`
- Existing Phase 3.3 Payment Allocation implementation
- Existing Phase 3.4 recurring/charge/invoice generation implementation
- `payments.Invoice`, `Payment`, `PaymentAllocation`
- `payments.services`, `allocation_service`, billing/invoice services and APIs
- `tenant.Tenant`, `Occupancy`, `Charge`
- Existing settlement calculation and PostgreSQL RLS

Current foundation is sufficient for an additive credit layer:

1. `Payment.invoice` is nullable, so an unlinked payment can already be represented.
2. `PaymentAllocation` is the canonical invoice-settlement relationship.
3. Payment has an `unallocated_amount` concept, but it currently ignores any amount explicitly reserved as prepaid credit.
4. Canonical payment creation rejects invoice overpayment; this behavior is protected.
5. Settlement currently reads payment allocations and must not count unapplied credit as invoice collection.
6. Existing financial tables are workspace-scoped and RLS-protected.

**Important audit correction:** an `AdvanceCreditApplication` must participate in invoice settlement calculations. Creating a separate credit-application record without extending the canonical invoice paid/outstanding calculation would leave the new money invisible to invoice state. Therefore Phase 3.8 explicitly extends the canonical financial-state calculation to include both `PaymentAllocation` and `AdvanceCreditApplication` as valid settlement components.

---

## 3. Terminology — LOCKED

### Advance billing

`Occupancy.billing_type = "advance"` means the billing period is billed before/at the service period. It is **not** a credit balance.

### Advance payment / prepaid credit

Money received but not currently settling an invoice, including an unallocated residual after invoice allocation.

Example:

```text
Payment ₹30,000
Invoice settlement ₹20,000
Remaining ₹10,000
        ↓
Advance Credit ₹10,000
```

The credit is a real financial state and must be auditable.

---

## 4. Architectural Decisions

### 4.1 New bounded financial objects

Create:

```text
AdvanceCredit
    ↓
AdvanceCreditApplication
    ↓
Invoice
```

`AdvanceCredit` is the prepaid principal. `AdvanceCreditApplication` records consumption against an invoice.

Do not store prepaid money inside `Invoice.paid_amount` or mutate historical Payment amounts.

### 4.2 Credit ownership

Credit is **tenant-scoped** and optionally occupancy-associated.

- Workspace is mandatory.
- Tenant is mandatory.
- Occupancy is optional context and must belong to the same tenant/workspace.
- Tenant scope allows valid prepaid money to survive an ended occupancy and be applied to a later invoice for the same tenant.

### 4.3 Source payment

Every credit must reference one source Payment uniquely.

No anonymous/manual credit is introduced in Phase 3.8. Manual financial adjustments belong to the later Credits/Debits/Adjustments phase.

### 4.4 Immutable financial records

After creation, source payment, tenant, occupancy, principal and application amount/references cannot be mutated. Corrections belong to explicit future refund/adjustment workflows.

---

## 5. Data Model

### 5.1 `AdvanceCredit`

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

Constraints:

- `original_amount > 0`
- all related objects belong to the same workspace
- optional occupancy belongs to the credit tenant
- source payment cannot create a second credit principal
- principal is immutable

Derived balance:

```text
available_credit = original_amount
                  - SUM(AdvanceCreditApplication.amount)
```

No mutable `remaining_amount` column is required.

### 5.2 `AdvanceCreditApplication`

Proposed fields:

```text
id
credit FK → AdvanceCredit
invoice FK → Invoice
amount Decimal(10,2)
created_at
```

Constraints:

- `amount > 0`
- credit and invoice are in the same workspace
- invoice tenant equals credit tenant
- application amount cannot exceed available credit
- application amount cannot exceed invoice outstanding
- application is immutable after creation

Indexes:

```text
(credit)
(invoice)
(credit, created_at)
```

Use a positive-amount database check constraint. Aggregate capacity remains a service-level invariant protected by row locks.

---

## 6. Payment Capacity & Double-Spend Rules

This is the most important integration point.

Once an unallocated payment amount is converted into an AdvanceCredit, that amount is **reserved** and cannot also be allocated directly through `PaymentAllocation`.

Canonical capacities become:

```text
Payment allocatable amount
  = payment amount
  - existing PaymentAllocation total
  - reserved AdvanceCredit principal
```

`Payment.unallocated_amount` must be updated to reflect this reserved amount.

Rules:

- Existing invoice payment overpayment validation remains protected.
- Credit creation can consume only currently unallocated payment capacity.
- Credit creation and normal payment allocation must lock the Payment before calculating capacity.
- A source payment cannot be allocated after its full remaining amount has been reserved as credit.
- Credit application does not create a new Payment and does not increase Payment amount.

---

## 7. Canonical Financial State Calculation

The current Invoice read-side derives paid/outstanding from `PaymentAllocation`. Phase 3.8 extends this canonical calculation to include prepaid-credit applications.

Define:

```text
invoice_settled_amount
  = SUM(PaymentAllocation.amount)
  + SUM(AdvanceCreditApplication.amount)
```

Then:

```text
Invoice outstanding
  = Invoice receivable - invoice_settled_amount
```

Compatibility `Invoice.paid_amount/status` must continue to be maintained by the canonical financial transition service, but must reflect the combined valid settlement amount.

The existing `Invoice.allocated_paid_amount` property may be retained for API compatibility only if its documented meaning is updated or a new canonical `settled_paid_amount` property is introduced. There must be one authoritative calculation internally.

This prevents the critical failure mode where an applied prepaid credit exists in the database but the invoice still appears unpaid.

---

## 8. Canonical Services

### 8.1 `create_advance_credit(...)`

Transaction:

1. Resolve Payment within workspace.
2. Lock Payment with `select_for_update()`.
3. Resolve/validate Tenant and optional Occupancy.
4. Calculate current unallocated payment capacity, including existing reserved credit.
5. Reject zero/negative capacity.
6. Reject duplicate source-payment credit principal.
7. Create `AdvanceCredit` atomically.
8. Do not change invoice state.

### 8.2 `apply_advance_credit(...)`

Transaction:

1. Lock AdvanceCredit.
2. Lock target Invoice using deterministic lock ordering.
3. Validate workspace and tenant equality.
4. Recalculate available credit from applications.
5. Recalculate invoice outstanding from allocations + prior credit applications.
6. Reject over-application.
7. Create immutable `AdvanceCreditApplication` atomically.
8. Recalculate invoice financial state through the canonical financial transition service.
9. Return application, remaining credit and invoice state.

No Payment is created.

### 8.3 Allocation integration

`allocate_payment(...)` must account for reserved credit when calculating payment capacity. Otherwise a race could spend the same money both as a credit and as an invoice allocation.

---

## 9. Financial Examples

### Full advance payment

```text
Payment ₹20,000
No invoice
↓
AdvanceCredit ₹20,000
↓
Future Invoice ₹20,000
↓
Apply credit ₹20,000
↓
Invoice settled ₹20,000
Credit available ₹0
```

### Residual prepaid balance

```text
Payment ₹30,000
Invoice A settlement ₹20,000
↓
Reserved residual ₹10,000
↓
AdvanceCredit ₹10,000
↓
Invoice B ₹15,000
↓
Apply credit ₹10,000
↓
Invoice B outstanding ₹5,000
```

### Partial invoice + credit

```text
Invoice ₹20,000
PaymentAllocation ₹5,000
AdvanceCreditApplication ₹7,000
↓
Invoice settled ₹12,000
Invoice outstanding ₹8,000
Status PARTIAL
```

---

## 10. Settlement & Reporting Rules

Unapplied credit is **not** invoice collection.

Therefore:

- Dashboard collections must not increase when credit is merely created.
- Invoice outstanding must not decrease until credit is applied.
- Applied credit must count as invoice settlement.
- Tenant available-credit reporting may expose unapplied balance additively.
- Current settlement totals remain backward compatible.
- Future settlement lifecycle may explicitly consume/refund available credit.

Security deposits remain a separate financial concept and must not be silently converted into prepaid rent credit.

---

## 11. API Contract

Additive endpoints, manager mutation / staff read:

```text
POST /api/advance-credits/
GET  /api/advance-credits/
GET  /api/advance-credits/<credit_id>/
POST /api/advance-credits/<credit_id>/apply/
```

Create request:

```json
{
  "payment": 123,
  "tenant": 45,
  "occupancy": 67
}
```

Apply request:

```json
{
  "invoice": 456,
  "amount": "10000.00"
}
```

Backend returns authoritative amounts: original, available, applications and updated invoice state.

No tenant-facing mutation API or UI redesign in this phase.

---

## 12. Permissions & Workspace Isolation

- Mutation: `WorkspaceManagerPermission`
- Read: `WorkspaceStaffPermission`
- Every service independently enforces workspace scope.
- Application-level authorization remains mandatory with RLS.

New tables:

```text
payments_advancecredit
payments_advancecreditapplication
```

Both must be ENABLED and FORCED under PostgreSQL RLS.

RLS must prevent cross-workspace reads and writes through both direct and relationship-based access.

`enable_workspace_rls` must include both tables.

---

## 13. Migration Strategy

Additive migrations only.

Create the two new tables, indexes and positive-amount constraints, then apply RLS policies.

Do **not** destructively modify historical Payment/Invoice/PaymentAllocation records.

Do **not** automatically backfill historical payments into credits. Historical attribution may be ambiguous and must never be guessed.

Migration verification is mandatory:

```text
makemigrations --check --dry-run
migration graph
migrate
RLS enable/force
```

---

## 14. Testing Requirements

### Domain

- Full unlinked payment → credit.
- Residual payment → credit.
- Zero residual rejected.
- Duplicate source-payment credit rejected.
- Tenant/workspace mismatch rejected.
- Occupancy mismatch rejected.
- Available credit derived from applications.
- Credit application cannot exceed credit.
- Credit application cannot exceed invoice outstanding.
- Applied credit changes invoice paid/outstanding/status correctly.
- Credit creation does not change invoice state.
- Credit application creates no Payment.

### Concurrency

- Concurrent credit applications cannot overspend one credit.
- Concurrent allocation and credit reservation cannot overspend one Payment.
- Concurrent credit application and Payment allocation cannot over-settle an Invoice.
- Retry cannot create duplicate credit principal.

### Workspace/RLS

- Cross-workspace create/read/apply blocked.
- RLS blocks direct cross-workspace access.
- Related tenant/occupancy/invoice mismatch blocked.

### Regression

- Partial payments.
- Advance billing.
- Arrears billing.
- Payment allocation.
- Recurring billing.
- Charge generation.
- Invoice generation.
- Dashboard financial totals.
- Final settlement calculation.

### CI gate

- Full Django suite.
- Django system checks.
- Migration graph/check/apply.
- PostgreSQL integration.
- Workspace RLS tests.
- CI GREEN on final commit.

---

## 15. Explicit Non-Goals

Not in Phase 3.8:

- Generic credits/debits/adjustments.
- Refunds.
- Credit expiry.
- Promotional/store credit.
- Gateway/webhook integration.
- UPI/payment links.
- Reconciliation.
- Ledger/GL entries.
- Tax/GST treatment.
- Automatic credit-allocation policy engine.
- Historical automatic backfill.
- Tenant-facing mutation UI/API.

---

## 16. Implementation Order

```text
Architecture audit + model/FK/migration audit
        ↓
Models + migrations
        ↓
Payment capacity integration
        ↓
Canonical settlement calculation
        ↓
Advance-credit service
        ↓
Credit-application service
        ↓
Serializers + additive API
        ↓
Domain/concurrency/workspace tests
        ↓
PostgreSQL + RLS integration
        ↓
Full regression
        ↓
Migration/system checks
        ↓
CI GREEN
        ↓
Final financial/security audit
        ↓
Mark COMPLETE
```

No implementation should begin outside this locked scope without an explicit architecture update.

---

## 17. Completion Gate

Phase 3.8 is complete only when:

1. AdvanceCredit and AdvanceCreditApplication exist and are workspace-safe.
2. Advance credit is clearly distinct from advance billing.
3. Every credit has an auditable source Payment.
4. Payment reserved-for-credit capacity cannot be double-spent.
5. Credit balance is derived from immutable applications.
6. Applied credit participates in canonical invoice paid/outstanding/status calculation.
7. Credit application is transactional and concurrency-safe.
8. Existing partial/advance/arrears workflows remain green.
9. PaymentAllocation remains correct.
10. Dashboard/settlement do not falsely treat unapplied credit as invoice collection.
11. RLS protects both new tables.
12. Cross-workspace access is blocked.
13. Full regression is green.
14. Migration checks are green.
15. CI is GREEN on the final commit.
16. Final financial integrity audit passes.

---

## 18. Final Architecture Decision

### KEEP 🔒

- Payment nullable-invoice foundation.
- PaymentAllocation as an invoice settlement primitive.
- Partial payments.
- Advance billing.
- Arrears billing.
- Existing invoice lifecycle.
- Workspace/RBAC/RLS.
- Existing settlement foundation.

### EXTEND ➕

- `AdvanceCredit`.
- `AdvanceCreditApplication`.
- Payment allocatable-capacity calculation.
- Canonical combined invoice settlement calculation.
- Credit creation/application services.
- Additive staff/manager APIs.
- Available prepaid-balance read model.

### DO NOT REWRITE ❌

- Property hierarchy.
- Tenant/Occupancy architecture.
- Existing Invoice architecture.
- Existing PaymentAllocation architecture.
- Recurring billing architecture.
- Existing validated workflows.
- UI architecture.

### Golden Rule

> **Advance money received must be represented as explicit, auditable prepaid credit and must never be silently hidden inside invoice payment state.**

**Status: LOCKED 🔒**
