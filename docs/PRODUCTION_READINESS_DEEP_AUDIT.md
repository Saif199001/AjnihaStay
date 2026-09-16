# AjnihaStay — Production Readiness Deep Audit

**Audit ID:** PROD-AUDIT-BASELINE-001  
**Repository:** `Saif199001/AjnihaStay`  
**Audited branch:** `production-branch`  
**Audited baseline:** `3e8b7dd40cdb1e5170a33f354ac95587cda38706`  
**Latest verified CI at audit:** Django CI #985 — GREEN  
**Purpose:** Record the current production-readiness gaps before implementation/hardening.

---

## 1. Executive Summary

The current AjnihaStay backend has a strong foundation: workspace/multi-tenancy, RBAC, RLS architecture, property/unit hierarchy, occupancy, financial models, ledger, adjustments, advance-credit models, KYC, leasing, applications, dashboard/reporting and extensive tests are already present.

However, **green CI does not yet mean production-ready**. The audit identified several gaps where the implementation is either incomplete, has competing authorities, lacks sufficient database-level protection, or needs a production deployment/security gate.

The most important production blockers are:

1. Full RLS coverage is incomplete.
2. Recurring billing does not yet have one canonical atomic orchestration authority.
3. The recurring charge generator lacks the `post_ledger` orchestration contract needed by the canonical recurring flow.
4. Advance-payment/overpayment handling is not a complete end-to-end collection workflow.
5. CI does not currently provide a complete production-branch/deployment security gate.
6. Occupancy and billing-schedule concurrency/invariant hardening needs completion.

The correct strategy is **not a rewrite**. Existing validated financial, tenancy, leasing and KYC behavior must be preserved. Missing capabilities should be recovered from verified repository history where available, then integrated and protected with contract/concurrency tests.

---

# 2. Audit Status Legend

- **FOUND / VERIFIED:** implementation exists and evidence was inspected.
- **PARTIAL:** implementation exists but the complete contract is not closed.
- **GAP:** required production behavior is missing or incomplete.
- **RISK:** consequence if left unresolved.
- **PRODUCTION BLOCKER:** should be closed before production use.

---

# 3. P0 — Production Blockers

## P0-01 — Incomplete PostgreSQL RLS Coverage

### Area
Security / Multi-tenancy / Database isolation

### Current state
The current `workspaces/management/commands/enable_workspace_rls.py` enables and forces RLS for a limited set of tables, including properties, units, tenants/occupancy/charges, invoices, payments, allocations, billing schedules and advance-credit tables.

The current command does not cover all workspace-owned sensitive domain tables now present in the project, including financial adjustments, final settlements, financial ledger entries, applications/applicants/events, KYC entities/events, leasing entities/events and related contract data.

### Gap
Application-level workspace filtering and permission checks are not sufficient as the final isolation boundary for every sensitive workspace-owned table. The operational RLS enable/force command must cover the complete tenant-scoped table inventory and every table must have an appropriate workspace policy.

### Risk
A missed RLS table can become a cross-workspace data-isolation vulnerability if a future query path forgets an application-level workspace filter or if a lower-level access path is introduced.

### Required fix
Create a canonical tenant-scoped RLS inventory and make the enable/force command cover every required table. Verify both `USING` and `WITH CHECK` policies, workspace context handling, migration ordering and non-owner/non-superuser production DB role requirements.

### Required tests
- Every expected tenant-scoped table has RLS enabled.
- Every expected table has FORCE RLS.
- Policies exist with correct workspace predicate.
- Cross-workspace reads return no rows.
- Cross-workspace inserts/updates are rejected.
- Missing workspace context fails closed.
- RLS remains effective outside normal request views.

### Status
**RED — PRODUCTION BLOCKER**

---

## P0-02 — Recurring Billing Has Competing Orchestration Authorities

### Area
Financial Engine / Recurring Billing

### Current state
The repository contains `payments/charge_generation_service.py` and `payments/recurring_invoice_service.py`. The current recurring invoice service performs invoice creation, charge creation and schedule advancement itself.

A later repository source candidate contains a more complete canonical `recurring_billing_service.py` intended to own the atomic charge + invoice orchestration. The current branch does not yet have that canonical boundary in place.

### Gap
There is not one authoritative recurring occurrence transition:

`Schedule → Occurrence → Charge → Invoice → Ledger → next_run_date`

Competing service paths can create ambiguity around idempotency, charge/invoice consistency, ledger timing and schedule advancement.

### Risk
Duplicate invoices/charges, partially completed occurrences, incorrect ledger linkage, schedule drift, or inconsistent replay behavior under retries/concurrent execution.

### Required fix
Recover the verified canonical recurring billing implementation from repository history rather than inventing a second design. Make one service the authoritative atomic orchestration boundary. Keep the existing public compatibility entry point only as a wrapper where required.

### Required tests
- First occurrence creates exactly one charge and invoice.
- Exact replay returns the existing occurrence.
- Charge exists/invoice missing recovery is deterministic.
- Concurrent execution creates one occurrence.
- Schedule advances exactly once.
- Checkout boundary is respected.
- Ledger events are canonical and correctly linked.

### Status
**RED — PRODUCTION BLOCKER**

---

## P0-03 — Recurring Charge `post_ledger` Contract Is Not Closed

### Area
Financial Engine / Ledger orchestration

### Current state
Current `generate_charge_from_schedule()` does not expose the keyword-only `post_ledger` control required by the canonical recurring orchestration. The intended later source passes `post_ledger=False` during the recurring occurrence flow and posts the canonical charge ledger event only after the invoice exists.

### Gap
The recurring orchestrator cannot safely suppress the lower-level charge ledger transition and then create the final canonical linked ledger event.

### Risk
Duplicate ledger events, incorrectly linked charge ledger entries, runtime signature errors, or financial-event ordering problems.

### Required fix
Use the verified later contract:

`generate_charge_from_schedule(..., *, post_ledger=True)`

and pass the value through to the underlying charge creation service. Recurring orchestration must call it with `post_ledger=False` and own the final canonical ledger event.

### Required tests
- Direct charge generation posts its normal ledger event.
- Recurring generation suppresses the lower-level event.
- Exactly one canonical recurring charge ledger event is created.
- Ledger event references the final invoice where required.
- Replay does not create duplicate events.

### Status
**RED — PRODUCTION BLOCKER**

---

## P0-04 — Advance Payment / Overpayment Flow Is Not End-to-End

### Area
Payments / Advance Billing

### Current state
The current payment-recording path requires an invoice and rejects an amount greater than the invoice's current outstanding balance. The separate advance-credit service expects an existing payment with unallocated capacity.

This means the natural business workflow:

`Payment ₹10,000 → current invoice ₹7,000 → ₹7,000 allocated + ₹3,000 advance`

is not represented as one complete collection transition by the current payment-recording service.

### Gap
The domain has `AdvanceCredit` and `AdvanceCreditApplication`, but the end-to-end overpayment/prepayment intake path is not fully closed.

### Risk
Users may be unable to correctly record real-world prepaid/overpaid collections, leading to manual workarounds or incorrect financial state.

### Required fix
Define the canonical payment-intake semantics for:
- exact invoice payment;
- partial payment;
- overpayment;
- unapplied payment;
- explicit advance payment;
- later credit application.

Preserve existing partial-payment and settlement semantics. Do not mutate invoice receivable merely because cash was received in advance.

### Required tests
- Exact payment.
- Partial payment.
- Overpayment with automatic or explicit advance split according to the final contract.
- Pure advance payment without invoice.
- Advance applied to future invoice.
- Concurrent advance application.
- Refund interaction.
- Ledger events for cash receipt, allocation and credit creation.

### Status
**RED — PRODUCTION BLOCKER**

---

## P0-05 — Production CI / Security Gate Is Incomplete

### Area
CI/CD / Deployment security

### Current state
The latest verified CI run #985 is green and performs migration graph checks, migration consistency checks, migrations, RLS enablement, the Django test suite and Django system checks.

However, the workflow does not provide a complete production security gate equivalent to a strict deployment check, and the current push-trigger configuration does not provide the same direct push coverage for the working production branch as a dedicated production gate should.

### Gap
CI must explicitly validate production deployment safety, not only application tests.

### Required fix
Add a production-grade gate including, as appropriate:
- `python manage.py check --deploy --fail-level WARNING`;
- migration checks;
- RLS verification;
- full test suite;
- dependency/security checks where adopted;
- production branch trigger/protection alignment;
- fail-closed environment configuration checks.

### Required tests
CI itself must fail when a production security warning is introduced.

### Status
**RED — PRODUCTION BLOCKER**

---

# 4. P1 — High Priority Hardening

## P1-01 — Occupancy Concurrency / Capacity Race

### Current state
Occupancy validation checks date overlap, capacity and active unit/subunit state. The validation is primarily application-level.

### Gap
Concurrent occupancy creation can potentially pass validation before either transaction commits.

### Risk
Overbooking or exceeding unit/subunit capacity under concurrent requests.

### Required fix
Use the existing occupancy semantics and add a database/transaction-level concurrency strategy appropriate to PostgreSQL, with row locking or an exclusion/locking design where applicable. Do not change historical occupancy semantics unnecessarily.

### Required tests
Two concurrent occupancy attempts for the same capacity boundary must result in only the valid number of active occupants.

### Status
**ORANGE — HIGH PRIORITY**

---

## P1-02 — BillingSchedule Invariant Hardening

### Current state
Billing schedules validate positive amounts, next-run dates relative to check-in and active/inactive occupancy relationships.

### Gap
The later hardened contract is not fully present on the current branch, including:
- monthly `anchor_day` derivation/validation;
- daily schedules requiring `anchor_day=None`;
- automatic deactivation when the next run reaches/exceeds checkout;
- database uniqueness for one active schedule per occupancy;
- complete locking during schedule updates/generation.

### Risk
Duplicate active schedules, incorrect monthly recurrence, post-checkout generation and schedule drift.

### Required fix
Recover and verify the later BillingSchedule hardening rather than duplicating it.

### Required tests
Daily/monthly anchor behavior, duplicate-active schedule race, checkout boundary, inactive occupancy, schedule update concurrency.

### Status
**ORANGE — HIGH PRIORITY**

---

## P1-03 — Financial State Has More Than One Mutation Helper

### Current state
`calculate_invoice_financial_position()` is used as the canonical financial-position calculation. However, both adjustment services and the general payment services contain functions that update invoice `paid_amount` and `status` from that position.

### Gap
There is not yet a single obvious canonical transition boundary for all invoice financial-state mutations.

### Risk
Future features can introduce divergent status/paid-amount calculations.

### Required fix
Keep `calculate_invoice_financial_position()` as the canonical calculation and converge state transitions behind one carefully tested service boundary. Do not directly rewrite model semantics or remove validated protections until all call sites are audited.

### Required tests
Every payment/allocation/advance/adjustment/refund transition must yield the same canonical invoice position.

### Status
**ORANGE — ARCHITECTURAL HARDENING**

---

## P1-04 — Legacy KYC Document Path Remains

### Current state
The new KYC domain has private-storage/lifecycle architecture, but the Tenant model still contains the legacy `id_document` file field.

### Gap
There are two possible identity-document storage paths:

`Tenant.id_document` → generic file storage

and

`KycDocument` → controlled/private KYC storage.

### Risk
A legacy service/API path could accidentally store sensitive identity documents through the weaker storage path.

### Required fix
Make the KYC document model/service the only supported identity-document path. Audit every caller of tenant creation/update and remove or quarantine the legacy field only after compatibility/data migration analysis.

### Required tests
No supported API/service can create a new identity document through the legacy field. Existing data migration/compatibility behavior must be verified.

### Status
**ORANGE — SECURITY HARDENING**

---

## P1-05 — Background/Automation Workspace Context

### Current state
Normal workspace permissions establish the PostgreSQL workspace context for API requests.

### Gap
Future scheduled billing, automation, management commands and worker execution must explicitly establish workspace context before touching tenant-scoped data.

### Risk
Background execution can bypass the request-level workspace context assumptions.

### Required fix
Define a standard workspace-scoped execution wrapper for non-request operations. Every automation/worker command must require an explicit workspace and establish RLS context inside the transaction.

### Required tests
Worker execution with correct workspace succeeds; missing/incorrect context fails closed; cross-workspace access is rejected.

### Status
**ORANGE — AUTOMATION SECURITY REQUIREMENT**

---

## P1-06 — Authorization Role Source Needs Consolidation

### Current state
User-level role concepts and workspace membership roles coexist. The workspace permission system correctly ranks membership roles (`staff`, `manager`, `admin`, `owner`) for workspace authorization.

### Gap
The existence of multiple role concepts can create ambiguity about which role is authoritative.

### Risk
Future endpoints may accidentally use a user-level role instead of workspace membership role, causing privilege errors.

### Required fix
Document and enforce workspace membership as the authoritative workspace authorization source. Audit endpoints/services for direct role checks.

### Required tests
Cross-workspace and per-role authorization matrix across every mutation endpoint.

### Status
**ORANGE — AUTHORIZATION HARDENING**

---

## P1-07 — API Contract Governance Is Partial

### Gap
Core domain services exist, but error formats, endpoint authorization, mutation boundaries, idempotency expectations and compatibility behavior need a complete contract inventory.

### Required fix
Create an API contract matrix for every endpoint:
- authentication;
- workspace resolution;
- required role;
- input validation;
- workspace scoping;
- idempotency behavior;
- financial side effects;
- ledger effects;
- error status/schema;
- concurrency expectations.

### Status
**ORANGE — API HARDENING**

---

# 5. P2 — Production Quality / Scale

## P2-01 — Repository Hygiene

Tracked Python cache artifacts (`__pycache__`, `.pyc`) are present even though `.gitignore` already ignores them.

### Gap
Previously committed generated artifacts remain tracked.

### Fix
Remove tracked generated artifacts without changing application behavior.

### Status
**YELLOW — CLEANUP**

---

## P2-02 — Database Query / Index Audit

The dashboard and financial services already use deliberate query patterns, but production-scale query profiling should cover:
- occupancy queries;
- invoice aging;
- payment/allocation aggregation;
- ledger reporting;
- dashboard period queries;
- KYC/lease history;
- recurring billing lookup by schedule + occurrence.

### Status
**YELLOW — SCALE HARDENING**

---

## P2-03 — Observability

Production needs structured logs and monitoring for:
- recurring billing failures;
- payment failures;
- RLS/context failures;
- KYC delivery failures;
- background job failures;
- ledger conflicts;
- repeated idempotency conflicts.

### Status
**YELLOW — OPERATIONS**

---

## P2-04 — Backup / Restore Verification

A production database strategy must include verified backup, restore and recovery procedures, not merely provider-level backups.

### Status
**YELLOW — OPERATIONS**

---

## P2-05 — Deployment Runbook

Production deployment should have a documented sequence covering migrations, RLS policy state, DB role requirements, environment variables, static/media configuration, health checks, rollback and post-deployment verification.

### Status
**YELLOW — OPERATIONS**

---

## P2-06 — Dependency / Security Scanning

Introduce a repeatable dependency vulnerability/security review and keep it separate from application functional tests.

### Status
**YELLOW — SECURITY OPERATIONS**

---

## P2-07 — Rate Limit Tuning

DRF throttling exists, but production endpoints should have explicit rate-limit expectations for authentication, password reset, sensitive document delivery and expensive reporting operations.

### Status
**YELLOW — SECURITY HARDENING**

---

# 6. Areas Audited and Currently Strong

These areas should be preserved unless a specific audit failure requires change:

### Workspace / Multi-tenancy
Workspace membership resolution, workspace-scoped service patterns and PostgreSQL workspace context form a strong foundation.

### RBAC
Workspace membership roles provide a clear role-ranking model and are already used by workspace permission classes.

### Financial Models
Invoice, Payment, PaymentAllocation, AdvanceCredit, AdvanceCreditApplication and FinancialAdjustment contain substantial validation, immutability and transactional protections.

### Ledger
The ledger service provides deterministic event keys, replay handling, conflict detection, locking and immutable financial-event recording.

### Leasing
Lease lifecycle, contract versions, renewals, notices and lifecycle history have dedicated domain boundaries and tests.

### Applications
Applicant/application lifecycle and append-only application event architecture are established.

### KYC
The modern KYC domain has private-storage-oriented architecture, lifecycle validation and immutable event history. The main remaining issue is removing the legacy document path.

### Dashboard / Reporting
The dashboard has an established canonical query budget and financial-position based reporting behavior. Avoid changing it unless a specific regression or production-scale issue is demonstrated.

---

# 7. Recommended Closure Order

The audit should be converted into implementation milestones in this order:

```text
AUDIT BASELINE
    ↓
P0-01 RLS coverage
    ↓
P0-02/P0-03 canonical recurring billing
    ↓
P0-04 advance-payment workflow
    ↓
P0-05 production CI/security gate
    ↓
P1-01 occupancy concurrency
    ↓
P1-02 BillingSchedule hardening
    ↓
P1-03 financial transition consolidation
    ↓
P1-04 KYC legacy-path closure
    ↓
P1-05 background workspace context
    ↓
P1-06 authorization audit
    ↓
P1-07 API contract audit
    ↓
P2 production operations
    ↓
FINAL PRODUCTION READINESS AUDIT
```

Every milestone must follow:

`Architecture → Existing-source/history audit → Implementation → Tests → Real integration → CI Green → Freeze baseline`

---

# 8. Important Implementation Rule

**Do not merge the later `consolidation/production-code` branch wholesale.**

Repository history shows a later source line containing several relevant hardening commits, but that branch is ahead of the current baseline by many commits and contains historical experiments/fixes. Individual implementations must be inspected, their tests identified, and their CI evidence verified before porting.

This avoids reintroducing previously discovered regressions.

---

# 9. Final Audit Verdict

### Current state
**Strong backend foundation, but not yet production-grade.**

### Current CI
**GREEN** at the audited baseline.

### Production readiness
**NOT READY YET** due primarily to RLS completeness, recurring billing canonicalization, advance-payment workflow closure and production security/deployment gating.

### Strategy
**HARDEN, DO NOT REBUILD.**

Existing validated contracts are the baseline. The goal is to close the identified gaps without regressing workspace isolation, financial semantics, partial payments, advance handling, arrears, occupancy, leasing, KYC or ledger integrity.

---

**Audit baseline:** `PROD-AUDIT-BASELINE-001`  
**Next phase:** P0 forensic closure and verified implementation.
