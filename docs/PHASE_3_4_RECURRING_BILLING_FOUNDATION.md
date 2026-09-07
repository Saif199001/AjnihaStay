# Phase 3.4 — Recurring Billing Foundation

**Status: LOCKED**  
**Branch:** `phase-1/workspace-multitenancy`  
**Phase:** 3 — Financial Architecture  
**Depends on:** Phase 3.3-C Payment Allocation Read-Side Canonicalization

## 1. Objective

Establish the domain foundation for configurable recurring billing without prematurely implementing a full automated charge/invoice generation engine.

The target architecture is:

`Occupancy / Billing Configuration → Billing Schedule → Future Charge Generation → Future Invoice Generation → Payment Allocation`

Phase 3.4 owns the **billing schedule/configuration truth and execution seam**. Future charge and invoice generation milestones will consume this foundation. Payment allocation remains the canonical representation of money applied to invoices and is not redesigned here.

## 2. Architecture Audit Findings

The current financial/domain foundation already contains:

- `Occupancy.billing_type` with `advance` and `arrears` semantics.
- `Occupancy.billing_cycle` with `monthly` and `daily` semantics.
- `Occupancy.rent`, `next_due_date`, `check_in_date`, and optional `check_out_date`.
- `Charge` attached to an `Occupancy`, with typed charge, amount and charge date.
- `Invoice` attached to an `Occupancy`, with billing period, rent, charges, due date and canonical allocation-aware paid/due reads.
- Canonical payment allocation from Phase 3.3.

These existing fields and relationships are protected. Phase 3.4 must extend them rather than replace them.

## 3. In Scope

### 3.1 Billing schedule domain

Introduce a dedicated recurring billing schedule/configuration concept capable of representing:

- Workspace ownership/isolation.
- Occupancy association.
- Active/inactive lifecycle.
- Billing frequency/cycle compatible with currently supported monthly/daily behavior.
- Billing type compatible with advance/arrears behavior.
- Effective start date.
- Optional end date.
- Next scheduled billing date.
- Stable schedule identity and timestamps.

The model must be extensible for future property-specific and tenant-specific billing rules without requiring another core billing model.

### 3.2 Billing configuration semantics

The foundation must define deterministic semantics for:

- Which occupancy is billed.
- When a recurring period becomes due for processing.
- How the next billing date advances.
- How active/inactive schedules behave.
- How check-in/check-out boundaries constrain a schedule.
- How advance versus arrears is represented without duplicating the existing occupancy concept.

### 3.3 Financial transition boundary

Define the service/domain seam that future automation can call to process a billing period.

The seam must be designed so that future generation follows:

`Billing Schedule → Canonical Billing Service → Charge/Invoice state`

It must not allow model saves, signals, API views or scheduled jobs to become competing financial transition authorities.

### 3.4 Workspace and integrity protection

- Schedule records must be workspace-isolated.
- Occupancy and schedule must belong to the same workspace.
- Existing RLS architecture must be extended when the new table is introduced.
- Persisted schedule identity/ownership fields must not be freely mutable in ways that break financial history.
- Invalid dates/frequency/state combinations must be rejected at the domain and database levels where practical.

### 3.5 API/domain contract foundation

If an API surface is introduced in this milestone, it must expose only the stable schedule/configuration contract needed by the product. It must preserve existing tenant/occupancy/payment contracts and enforce existing RBAC rules.

### 3.6 Tests

Focused tests must cover:

- Schedule creation and workspace isolation.
- Valid frequency/billing-type combinations.
- Effective date and end-date validation.
- Active/inactive behavior.
- Next billing date progression semantics.
- Occupancy workspace mismatch rejection.
- Cross-workspace access/RLS.
- RBAC/API behavior if exposed.
- Existing Phase 0–3.3-C financial regression suite.

## 4. Explicitly Out of Scope

Phase 3.4 does **not** implement:

- Automatic charge generation for recurring periods.
- Automatic invoice generation for recurring periods.
- A background scheduler/Celery production job.
- Proration engine.
- Discounts.
- Credits/debits/adjustments.
- Late fees/grace-period engine.
- Deposits/refunds redesign.
- Utility meter billing engine.
- Commercial escalation/CAM/NNN billing rules.
- Payment allocation redesign.
- Ledger/accounting engine.
- Reconciliation engine.
- Payment gateway/UPI integrations.
- WhatsApp/SMS/email automation.
- AI billing decisions.

Those are later milestones and must not be pulled into this implementation opportunistically.

## 5. Locked Invariants

1. Existing `Occupancy.billing_type` and `Occupancy.billing_cycle` semantics remain valid and supported.
2. Existing tenant/occupancy lifecycle and date/capacity rules do not regress.
3. A recurring billing schedule belongs to exactly one workspace and one occupancy.
4. Cross-workspace schedule/occupancy relationships are rejected.
5. Schedule state is configuration truth; it is not itself a financial transaction.
6. No invoice or charge is considered generated merely because a schedule is due.
7. Future generation must pass through a canonical billing service rather than direct model/save/signal mutation.
8. Payment allocation remains the canonical paid-state representation established in Phase 3.3-C.
9. Existing partial payments, advance/unallocated payments and arrears behavior remain intact.
10. Schedule progression must be deterministic and safe against duplicate execution.
11. Historical financial records must not be rewritten merely to introduce recurring billing configuration.
12. Workspace isolation/RLS and existing RBAC remain non-negotiable.
13. No supported Phase 0–3.3-C behavior may regress.

## 6. Design Direction

### 6.1 Schedule versus financial records

A schedule describes **intent to bill periodically**. It must not be confused with a Charge or Invoice.

A future execution should be traceable to a schedule/period so duplicate processing can be prevented without changing existing financial truth models.

### 6.2 Existing occupancy defaults

Current occupancy creation supports monthly/daily and advance/arrears billing semantics. Phase 3.4 should treat those as backward-compatible defaults and provide a dedicated schedule abstraction for recurring behavior rather than removing or silently changing the occupancy fields.

### 6.3 Future extensibility

The foundation should leave room for future:

- recurring rent,
- recurring fixed charges,
- configurable billing periods,
- property-type billing rules,
- proration,
- escalation,
- utility/service charges,
- automated invoice generation.

These extensions must layer onto the schedule/configuration foundation rather than introduce parallel billing systems.

## 7. Completion Criteria

Phase 3.4 can be marked **COMPLETE** only after:

- Locked scope is implemented without scope creep.
- Migration(s) are valid and workspace/RLS protections are present.
- Domain/service/API contracts are covered by focused tests where applicable.
- Duplicate-execution and deterministic schedule progression risks are explicitly tested.
- Full regression suite is green.
- CI is GREEN on the final implementation commit.
- Final blueprint-compliance and workspace-isolation audit passes.
- Only then may the document status be changed from `LOCKED` to `COMPLETE`.

## 8. Next Milestone Boundary

After Phase 3.4 is complete, the next financial milestone may implement **recurring charge/invoice generation** using this schedule foundation and the canonical financial transition architecture.
