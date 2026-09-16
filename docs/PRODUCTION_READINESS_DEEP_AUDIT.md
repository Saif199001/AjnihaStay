# AjnihaStay — Production Readiness Deep Audit

**Audit ID:** PROD-AUDIT-BASELINE-001  
**Repository:** `Saif199001/AjnihaStay`  
**Audited branch:** `production-branch`  
**Previous baseline:** `3e8b7dd40cdb1e5170a33f354ac95587cda38706`  
**P0-01 final audited commit:** `7bd035ad55dcf355c122fb8765b3dbc1ab4ecb07`  
**P0-01 implementation baseline:** `b053b84445286cb9a4aad4e294743c2536696b46` + canonicalization migration commit above  
**Verified CI evidence:** Django CI #1066 — GREEN on implementation baseline `b053b84445286cb9a4aad4e294743c2536696b46`  
**Purpose:** Record production-readiness gaps and formally close/freeze completed checkpoints.

---

## 1. Executive Summary

The AjnihaStay backend has a strong foundation: workspace/multi-tenancy, RBAC, PostgreSQL RLS architecture, property/unit hierarchy, occupancy, financial models, ledger, adjustments, advance-credit models, KYC, leasing, applications, dashboard/reporting and extensive tests are already present.

The production-readiness hardening remains an incremental effort, not a rewrite. Existing validated financial, tenancy, leasing and KYC behavior must be preserved while remaining gaps are closed through verified implementation, contract tests and CI evidence.

**P0-01 — PostgreSQL RLS coverage is now CLOSED and FROZEN.** The deployment-time RLS inventory now covers all 26 workspace-owned tables identified by the audit, including `kyc_kycdocumentevent`. The historical KYC document-event migration used the legacy `app.current_workspace_id` setting, so a forward migration was added to canonicalize that policy to the project-wide `app.workspace_id` transaction-local context without rewriting historical migrations. CI #1066 verified migration graph consistency, migrations, RLS enablement and the full test suite with **665 tests passed**.

The remaining P0 production blockers are:

1. Recurring billing does not yet have one canonical atomic orchestration authority.
2. The recurring charge generator's `post_ledger` orchestration contract is not yet closed.
3. Advance-payment/overpayment handling is not yet a complete end-to-end collection workflow.
4. CI/deployment still needs a complete production security gate.

P1 concurrency, invariant, authorization, KYC legacy-path and API-contract hardening remains after the P0 sequence.

---

# 2. Audit Status Legend

- **FOUND / VERIFIED:** implementation exists and evidence was inspected.
- **PARTIAL:** implementation exists but the complete contract is not closed.
- **GAP:** required production behavior is missing or incomplete.
- **RISK:** consequence if left unresolved.
- **PRODUCTION BLOCKER:** should be closed before production use.
- **CLOSED / FROZEN:** implementation, audit evidence and CI evidence have been verified for the checkpoint; future work must not silently alter the frozen contract.

---

# 3. P0 — Production Blockers

## P0-01 — PostgreSQL RLS Coverage

### Area
Security / Multi-tenancy / Database isolation

### Final audited state
**CLOSED / FROZEN — P0-01-RLS-FROZEN-001**

The deployment-time command `workspaces/management/commands/enable_workspace_rls.py` now contains the authoritative inventory of **26 workspace-owned tables** and enables **RLS + FORCE RLS** for every table in that inventory. The inventory includes financial adjustments, payment refunds, ledger entries, applications/applicants/events, leasing, all modern KYC entities/events and agreement links, including `kyc_kycdocumentevent`.

The canonical workspace context remains the transaction-local PostgreSQL setting `app.workspace_id`. KYC RLS policies in `0005_rls_workspace_isolation.py` already use that canonical setting for the modern KYC tables.

### Final blocker found during audit
`kyc/migrations/0003_document_lifecycle_history.py` historically created `KycDocumentEvent` with a policy using the legacy setting `app.current_workspace_id`. Historical migrations were intentionally not rewritten because they may already be applied in deployed databases.

### Final fix
Added `kyc/migrations/0006_canonicalize_document_event_rls.py`, dependent on `0005_rls_workspace_isolation`, which:

- keeps `kyc_kycdocumentevent` RLS enabled;
- keeps `FORCE ROW LEVEL SECURITY` enabled;
- replaces the historical policy safely;
- uses the canonical fail-closed predicate:
  `workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::bigint`;
- applies the same predicate to both `USING` and `WITH CHECK`;
- preserves a reverse migration that restores the historical policy contract.

### Evidence
- RLS inventory: `workspaces/management/commands/enable_workspace_rls.py` — **26 tables**.
- Historical mismatch: `kyc/migrations/0003_document_lifecycle_history.py`.
- Canonical KYC policies: `kyc/migrations/0005_rls_workspace_isolation.py`.
- Canonicalization migration: `kyc/migrations/0006_canonicalize_document_event_rls.py`.
- CI #1066: GREEN.
- CI #1066 verified migration graph, `makemigrations --check --dry-run`, migrations, RLS enablement and the full Django test suite.
- CI #1066 test result: **665 tests passed**.
- CI RLS command result: **Workspace row-level security enabled and forced for 26 tables.**

### Final verdict
**CLOSED / FROZEN — P0-01-RLS-FROZEN-001**

The RLS implementation may be extended only through an explicit audit of any newly introduced workspace-owned table. Any future change to workspace context, RLS policy semantics or the authoritative inventory requires a new checkpoint rather than silently modifying this frozen baseline.

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
The latest verified implementation CI run #1066 is green and performs migration graph checks, migration consistency checks, migrations, RLS enablement, the Django test suite and Django system checks.

However, the workflow does not yet provide a complete production security gate equivalent to a strict deployment check.

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
The modern KYC domain has private-storage-oriented architecture, lifecycle validation and immutable event history. The historical document-event RLS setting mismatch has now been corrected through a forward migration without rewriting the historical migration.

---

# 7. Frozen Checkpoints

## P0-01-RLS-FROZEN-001

**Checkpoint:** Complete PostgreSQL workspace-isolation/RLS inventory and canonical context alignment.  
**Status:** **FROZEN**  
**Freeze basis:** RLS inventory = 26 tables; KycDocumentEvent canonicalization migration added; CI #1066 GREEN; 665 tests passed; migrations and deployment-time RLS enable/force command verified.  
**Freeze rule:** Any future modification to the workspace context setting, RLS policy semantics, or authoritative workspace-table inventory requires a new explicit audit/checkpoint.

---

# 8. Next Production-Hardening Order

1. **P0-02 — Recurring Billing canonical orchestration**
2. **P0-03 — Recurring charge `post_ledger` contract**
3. **P0-04 — Advance payment / overpayment workflow**
4. **P0-05 — Production CI / security gate**
5. **P1 concurrency and invariant hardening**
6. **P1 authorization/KYC/API contract hardening**
7. **P2 operational and scale hardening**

The frozen P0-01 contract should be treated as the security baseline for all subsequent work.