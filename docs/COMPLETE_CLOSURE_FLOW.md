# AjnihaStay — Complete Production Closure Flow

**Document:** `docs/COMPLETE_CLOSURE_FLOW.md`  
**Status:** LOCKED — Execution Roadmap  
**Version:** 1.0  
**Scope Branch:** `production-branch`  
**Production Truth:** Current `production-branch` only  
**Purpose:** Close all currently identified security issues, financial interaction gaps, transactional risks, and production hardening findings in functionality that is already implemented.

---

## 1. Purpose and Closure Definition

This document is the execution contract for the remaining closure work on the currently implemented AjnihaStay backend.

The objective is **not** to claim that the entire AjnihaStay product is complete. The objective is to make every already-built production-branch capability internally consistent, secure, workspace-isolated, transaction-safe, financially correct, and sufficiently regression-tested.

### Closure question

> For every functionality that is already implemented on `production-branch`, is there any remaining security vulnerability, workspace-isolation failure, financial-integrity problem, transactional race, API/domain contract mismatch, or production hardening issue?

If the answer is yes, the issue must be fixed, tested, verified in CI, and re-audited before final closure.

---

## 2. Mandatory Scope Rules

### 2.1 Production source of truth

Only the current `production-branch` is valid for implementation and verification.

Do **not** use as code truth:

- old branches
- old candidate branches
- historical implementations
- historical CI results
- old audit conclusions unless freshly reproduced on the current branch
- old commits as a substitute for current code
- `master` as a production implementation source

Historical references may appear inside documentation, but they do not override the current branch.

### 2.2 Work directly on the working branch

All closure implementation is performed on:

```text
production-branch
```

No new working branch is required for this closure flow. `master` is not modified as part of this work.

### 2.3 Intentionally excluded from this closure

The following are **not** closure blockers for this document because they are known incomplete product areas:

1. Accounts
2. Project Settings
3. India's first payment system — not yet built
4. Portals — not yet built
5. Any Blueprint feature that has not yet been implemented

A feature that is incomplete by design is a product roadmap item, not automatically a defect.

### 2.4 Included functionality

The closure audit covers functionality already implemented on `production-branch`, including:

- Workspace / multi-tenancy
- Membership / RBAC
- Property
- Unit / SubUnit
- Tenant
- Occupancy / leasing foundation
- Charge
- Invoice
- Payment intake
- Partial payment
- Overpayment
- Advance billing / advance credit
- Payment allocation
- Refunds
- Financial adjustments
- Late fees
- Recurring billing
- Final settlement
- Financial ledger
- Dashboard / financial read models
- Implemented KYC functionality
- Implemented Applications lifecycle
- API authorization
- Workspace isolation / RLS
- Transactional behavior
- Database constraints
- Tests and integration contracts
- CI / migration / deployment-related backend configuration

---

# 3. Locked Closure Sequence

The closure sequence is:

```text
P0-A RLS / Multi-Tenant Isolation
        ↓
P0-B Refund × Allocation × AdvanceCredit
        ↓
P0-C Dashboard Financial Truth
        ↓
P1 Functional Hardening
        ↓
P2 Repository + Security Hygiene
        ↓
Regression Test Expansion
        ↓
Real Restricted-DB-Role / RLS Validation
        ↓
Full CI Verification
        ↓
Final Deep Re-Audit
        ↓
Production Baseline Freeze
```

The order is intentional. Later stages must not be used to hide or bypass an earlier blocker.

---

# 4. P0-A — RLS / Multi-Tenant Isolation Closure

**Priority:** P0 / Security Blocker  
**Objective:** Make database-level workspace isolation complete and correct for every workspace-owned table.

## 4.1 Current risk to close

The current RLS setup enables/forces RLS across a broader set of workspace-owned tables than the currently defined fail-closed policy map covers.

This creates a gap between:

```text
RLS enabled/forced tables
```

and

```text
tables with verified workspace-aware policies
```

The closure must eliminate that mismatch.

## 4.2 Required implementation

Audit every workspace-owned table and verify:

- RLS is enabled where required.
- `FORCE ROW LEVEL SECURITY` is intentional where required.
- A correct `USING` policy exists.
- A correct `WITH CHECK` policy exists.
- The policy reads the transaction-local workspace context safely.
- Cross-workspace reads are blocked.
- Cross-workspace inserts are blocked.
- Cross-workspace updates are blocked.
- Cross-workspace deletes are blocked.
- Related-object workspace relationships remain consistent.
- Tables that do not have a direct `workspace_id` use a safe relationship path or an explicit policy strategy.

## 4.3 Critical pure-advance payment case

A payment may be invoice-less when it represents a pure advance.

Therefore the RLS policy for `payments_payment` must not assume that every payment obtains its workspace exclusively through an invoice.

The policy must support:

```text
Payment.workspace_id → workspace context
```

for invoice-less payments.

## 4.4 Tables requiring explicit coverage review

At minimum, review all currently force-enabled workspace-owned tables, including financial tables such as:

- Invoice
- Payment
- PaymentAllocation
- BillingSchedule
- AdvanceCredit
- AdvanceCreditApplication
- FinancialAdjustment
- PaymentRefund
- FinancialLedgerEntry

and non-payment workspace-owned tables such as:

- Property
- PropertyImage
- Unit
- UnitImage
- SubUnit
- Tenant
- Occupancy
- Charge
- Lease
- KYC records/files/history where workspace ownership applies
- Application records/events where workspace ownership applies

The final implementation must be based on the actual current migration/model inventory, not on this list alone.

## 4.5 RLS test contract

Add/strengthen tests proving:

1. Workspace A cannot read Workspace B data.
2. Workspace A cannot insert data belonging to Workspace B.
3. Workspace A cannot update Workspace B data.
4. Workspace A cannot delete Workspace B data.
5. Related objects cannot bypass workspace isolation.
6. Pure advance payments remain usable under RLS.
7. Advance credit remains usable under RLS.
8. Cross-workspace ledger records are blocked.
9. Cross-workspace KYC/application records are blocked.
10. Inactive membership does not become an RLS bypass.

## 4.6 Real database-role requirement

CI currently uses a PostgreSQL role with elevated capabilities, so normal CI RLS tests are not sufficient proof of real application-role isolation.

A dedicated restricted PostgreSQL role must be used for the final validation.

The restricted role must not have `BYPASSRLS`.

The validation must prove isolation against the actual database policy layer rather than only Django permissions.

## 4.7 P0-A exit criteria

P0-A is complete only when:

- Every workspace-owned table has a deliberate RLS policy strategy.
- Pure advance payment works under RLS.
- Cross-workspace CRUD is blocked at DB level.
- Regression tests pass.
- Restricted-role RLS validation passes.
- Full CI passes after implementation.
- No new isolation regression is found.

---

# 5. P0-B — Refund × Payment Allocation × AdvanceCredit Closure

**Priority:** P0 / Financial Integrity Blocker  
**Objective:** Make successful refunds reduce the real financial capacity of a payment before that payment can be allocated or converted into advance credit.

## 5.1 Current risk to close

The refund interaction was made settlement-aware, but payment capacity calculations also need to be refund-aware.

Without this, a payment could conceptually become:

```text
Payment = ₹10,000
Refunded = ₹4,000
Actually available cash = ₹6,000
```

while allocation/advance-credit capacity could still treat the original ₹10,000 as available.

That can cause double use of the same financial value.

## 5.2 Canonical capacity contract

The payment's actually available capacity must follow the equivalent of:

```text
Payment Amount
- Effective Payment Allocations
- Reserved Advance Credit
- Successful Refund Impact
= Actually Available Capacity
```

The exact implementation must reuse the project's canonical refund semantics rather than introducing a second incompatible refund algorithm.

## 5.3 Required interactions

Audit and fix all paths that consume payment capacity, including:

- Payment allocation
- AdvanceCredit creation
- Any other service that reserves or consumes payment value
- Refund processing
- Existing payment-to-advance-credit conversion

## 5.4 Required scenarios

At minimum test:

### Scenario A — Refund before allocation

```text
Payment 10k
Refund 4k
Attempt allocation 7k
→ must reject
```

### Scenario B — Refund before AdvanceCredit creation

```text
Payment 10k
Refund 4k
Attempt AdvanceCredit 7k
→ must reject
```

### Scenario C — Remaining capacity

```text
Payment 10k
Refund 4k
Allocate 6k
→ allowed
Remaining capacity → 0
```

### Scenario D — Existing allocation plus refund

Verify the remaining allocation capacity cannot exceed the effective unreversed payment value.

### Scenario E — AdvanceCredit plus refund

Verify available credit reflects refunds and cannot be applied twice.

### Scenario F — Refund after allocation / credit application

Verify canonical financial position, invoice status, available credit, and dashboard/reporting values remain consistent.

## 5.5 Transaction and concurrency requirements

The fix must preserve atomicity.

Where financial capacity is checked before mutation:

- lock the relevant payment/credit/invoice records as required
- calculate capacity from the locked state
- perform the mutation inside the same transaction
- recalculate affected invoice state through the canonical financial service
- post ledger events only after the financial fact is valid
- keep idempotency/replay behavior intact

Do not solve the issue by merely changing a read-only property while leaving the mutation race open.

## 5.6 P0-B exit criteria

P0-B is complete only when:

- Refund-aware payment capacity is canonical.
- Allocation cannot reuse refunded value.
- AdvanceCredit creation cannot reuse refunded value.
- Existing refund → allocation reversal remains correct.
- Existing refund → AdvanceCredit reversal remains correct.
- Concurrency behavior is covered where relevant.
- Ledger semantics remain valid.
- Regression tests pass.
- Full CI passes.

---

# 6. P0-C — Dashboard Financial Truth Closure

**Priority:** P0 / Financial Read-Model Blocker  
**Objective:** Ensure dashboard numbers use exactly the same financial semantics as invoice/detail canonical financial state.

## 6.1 Current risk to close

The dashboard currently aggregates financial values from read-model inputs that do not fully account for all canonical financial effects.

The closure must eliminate divergence between:

```text
Invoice / canonical financial position
```

and

```text
Dashboard financial totals
```

## 6.2 Canonical financial truth

Dashboard financial reporting must account for the same concepts used by the canonical invoice financial position, including as applicable:

```text
Base invoice receivable
+ applicable charges / late fees
+ applicable financial adjustments according to their semantics
+ effective payment allocations
+ effective AdvanceCredit applications
- effective refund impacts
= canonical financial position
```

The exact sign and classification of credit/debit/discount/waiver/write-off adjustments must follow the existing financial contract.

## 6.3 Required parity tests

At minimum test dashboard parity for:

1. Fully paid invoice.
2. Partial payment.
3. Overpayment with AdvanceCredit.
4. Refund after full payment.
5. Refund after partial payment.
6. AdvanceCredit application.
7. Financial adjustment.
8. Late fee.
9. Refund plus AdvanceCredit interaction.
10. Multiple workspaces.
11. Empty/zero-value reporting periods where applicable.

For each scenario, compare dashboard values against canonical service results.

## 6.4 No second financial engine

Do not build an independent financial calculation engine inside dashboard code.

Preferred contract:

```text
Canonical financial service
        ↓
Dashboard read model / aggregation
```

The dashboard may optimize reads, but it must not silently define different financial truth.

## 6.5 P0-C exit criteria

P0-C is complete only when:

- Refunds are reflected.
- Late fees are reflected according to the canonical receivable contract.
- Adjustments are reflected correctly.
- AdvanceCredit applications are reflected correctly.
- Dashboard and invoice/detail agree for the same financial facts.
- Workspace isolation remains intact.
- Regression tests pass.
- Full CI passes.

---

# 7. P1 — Functional Hardening

**Priority:** P1 / Production Hardening  
**Objective:** Close remaining interaction and semantic weaknesses in implemented modules after the three P0 blockers are resolved.

## 7.1 Occupancy concurrency / overlap

Audit occupancy creation/update/checkout for concurrent requests.

Verify:

- unit capacity cannot be exceeded under concurrent writes
- overlapping occupancy cannot be created where the business contract forbids it
- open-ended occupancy behaves correctly
- date-boundary cases are deterministic
- locks and database constraints complement each other

Where PostgreSQL constraints can enforce the invariant safely, prefer DB-level enforcement over application-only checks.

## 7.2 Adjustment zero-receivable semantics

Define the correct status behavior when adjustments reduce an invoice's adjusted receivable to zero without a conventional payment settlement.

Example:

```text
Invoice = 10k
Write-off = 10k
Outstanding = 0
```

The implementation must use an explicit existing status vocabulary or introduce a documented status only if the project architecture requires it.

Do not silently label a zero-receivable invoice as `paid` unless that is the agreed business meaning.

Required tests must distinguish:

- paid by payment
- settled by credit/waiver/write-off/discount
- still outstanding

## 7.3 Recurring service bypass surfaces

Review internal `post_ledger=False` or equivalent lower-level bypasses.

These mechanisms may be necessary for atomic orchestration, but they must not permit accidental public bypass of canonical financial contracts.

Verify:

- intended callers are controlled
- direct misuse is rejected or inaccessible at API boundary
- canonical orchestration remains the authoritative path
- ledger posting cannot be silently skipped in production workflows

## 7.4 Final settlement semantics

Review negative/positive final balances and tenant refund/retention direction.

Document exactly what each sign means.

Verify:

- deposit refund direction
- deposit retention
- tenant payable balance
- owner payable/refund balance
- ledger representation
- idempotency
- immutable settlement snapshot

## 7.5 Payment listing/reporting semantics

Review invoice-centric payment listing where invoice-less pure advance payments exist.

Decide and document whether:

- invoice payment endpoints intentionally show only invoice-linked payments, or
- reporting should expose advance receipts separately, or
- a combined financial receipt view is required.

This is primarily a contract/reporting hardening item unless a current user-facing invariant is already broken.

## 7.6 SubUnit lifecycle hardening

Review deactivation, capacity/rent changes, and interactions with existing occupancy.

Prevent changes that would invalidate already-created occupancy/financial facts.

---

# 8. P2 — Repository and Security Hygiene

**Priority:** P2 / Hygiene + Operational Hardening

## 8.1 Tracked Python cache artifacts

The repository currently contains tracked `__pycache__` / `.pyc` artifacts despite `.gitignore` excluding them.

Required cleanup:

- remove tracked cache artifacts
- keep ignore rules
- verify no new cache artifacts are tracked

This is repository hygiene, not a financial correctness blocker.

## 8.2 Production settings audit

Review current production configuration for:

- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- CORS
- CSRF trusted origins
- HTTPS redirect
- HSTS
- secure cookies
- content-type sniffing protection
- referrer policy
- JWT lifetime
- refresh rotation / blacklist
- API throttling
- database URL parsing
- Cloudinary configuration
- static/media handling
- environment variable defaults

The objective is to identify insecure production defaults, not to change settings blindly.

## 8.3 Permission / authorization audit

For every mutation endpoint:

- confirm workspace membership is required
- confirm minimum role is correct
- confirm object lookup is workspace-scoped
- confirm service layer repeats critical workspace/ownership validation
- confirm direct model operations cannot bypass essential invariants

---

# 9. Regression Test Expansion

After P0-A, P0-B, P0-C, P1 and P2 fixes, build a closure regression matrix.

## 9.1 Security / isolation matrix

Test:

- workspace A vs workspace B
- active vs inactive membership
- each relevant role
- API-level authorization
- service-level authorization
- DB-level RLS
- related-object traversal
- direct ORM access under restricted DB role

## 9.2 Financial interaction matrix

At minimum cover combinations of:

```text
Invoice
Payment
Partial Payment
Overpayment
AdvanceCredit
PaymentAllocation
Refund
Adjustment
LateFee
RecurringBilling
FinalSettlement
Ledger
Dashboard
```

Important interaction combinations:

- Payment → Allocation
- Payment → Overpayment → AdvanceCredit
- Payment → Refund → Allocation
- Payment → Refund → AdvanceCredit
- Allocation → Refund
- AdvanceCredit → Application → Refund
- Adjustment → Invoice state
- LateFee → Invoice state
- Recurring charge → Invoice → Payment
- Final settlement → outstanding financial state
- Any financial mutation → Ledger
- Any financial mutation → Dashboard read model

## 9.3 Idempotency / replay matrix

Verify repeated requests for:

- payment operations where idempotency exists
- refunds
- adjustments
- recurring generation
- ledger posting
- final settlement

Repeated execution must not create duplicate financial facts.

## 9.4 Failure atomicity matrix

For every multi-step financial operation, test a failure at each meaningful stage and verify:

```text
Either all required state changes commit,
OR no partial financial state remains.
```

Ledger entries must not imply a financial fact that did not commit.

---

# 10. Real Restricted-DB-Role / RLS Validation

This stage is mandatory even if normal CI is green.

## 10.1 Why

A test role with elevated PostgreSQL privileges can make RLS appear healthy while not proving real application-role enforcement.

## 10.2 Required validation

Create/use a controlled PostgreSQL role suitable for application access that:

- does not have `BYPASSRLS`
- has only required database/schema/table permissions
- executes through the same workspace-context mechanism used by the application

Validate:

1. Workspace A read cannot see Workspace B.
2. Workspace A write cannot affect Workspace B.
3. Pure advance payment works.
4. AdvanceCredit works.
5. Ledger access is isolated.
6. KYC/application access is isolated.
7. Related-table access cannot bypass workspace boundaries.

The validation must be repeatable and documented.

---

# 11. Full CI Verification

Every closure milestone that changes code must reach a successful CI run.

## 11.1 Required checks

At minimum:

- migration graph
- `makemigrations --check --dry-run`
- migrations
- RLS setup/validation
- Django system checks
- complete Django test suite
- any added restricted-role integration validation available to CI

## 11.2 Green CI rule

A green CI result means the current tested commit passed the configured CI checks.

It does **not** by itself prove:

- production configuration is correct
- real DB-role RLS is correct unless that test actually runs
- all hidden functional interactions are correct
- no untested race exists

Therefore CI is a required gate, not the final audit.

---

# 12. Final Deep Re-Audit

After all fixes and successful verification, perform a **fresh audit from current `production-branch`**.

Do not merely re-read the old audit.

## 12.1 Final audit questions

For every included module ask:

### Security

- Can another workspace access this data?
- Can an unauthorized role mutate this data?
- Can direct ORM/API paths bypass authorization?
- Can RLS be bypassed unintentionally?

### Data integrity

- Can impossible states be stored?
- Are immutable facts protected?
- Are model constraints and service validation aligned?

### Financial integrity

- Can money be counted twice?
- Can refunded money be reused?
- Can advance credit exceed available value?
- Can invoice status disagree with canonical position?
- Can dashboard totals disagree with invoice truth?
- Can ledger events describe a financial fact that did not actually happen?

### Transactional integrity

- Are multi-step mutations atomic?
- Are required rows locked before capacity/state checks?
- Are concurrency races covered?
- Are retries/idempotency safe?

### API contract

- Does the serializer accept only valid input?
- Does authorization match the service contract?
- Are workspace lookups scoped?
- Are read/write semantics consistent with domain rules?

### Operational hardening

- Are production security settings safe?
- Is repository hygiene clean?
- Are bypass/internal-only paths controlled?
- Are migrations and CI deterministic?

## 12.2 New finding rule

If the final re-audit discovers a new issue:

```text
Finding
  ↓
Classify severity
  ↓
Fix current production-branch code
  ↓
Add regression test
  ↓
Run CI
  ↓
Re-audit affected area
```

Do not declare closure while a newly discovered blocker remains.

---

# 13. Production Baseline Freeze

The project may receive a new closure baseline only after:

- P0-A passes
- P0-B passes
- P0-C passes
- P1 findings are resolved or explicitly documented as accepted non-blocking hardening items
- P2 hygiene/security checks are complete or explicitly documented
- regression suite passes
- restricted DB-role RLS validation passes
- full CI is green on current `production-branch`
- final deep re-audit finds no unresolved blocker/gap/security issue in scope

Then create a new uniquely numbered frozen checkpoint.

Suggested naming format:

```text
P0-A — RLS Isolation Closure
P0-B — Refund Capacity Closure
P0-C — Dashboard Financial Truth Closure
P1 — Functional Hardening Closure
P2 — Security & Repository Hygiene Closure
RC — Production Closure Regression
VAL — Restricted Role Validation
FINAL — Production Baseline Freeze
```

Each frozen checkpoint must record:

- exact branch
- exact commit SHA
- CI run number
- test result
- scope covered
- known non-blocking limitations
- explicit statement of what is frozen

---

# 14. Severity Rules

Use the following classification consistently:

### 🟢 PASS

Implemented behavior is internally consistent, tested, and no material issue was found.

### 🟡 HARDENING

Functionality works, but production-strengthening, clarity, defense-in-depth, or edge-case improvements remain.

### 🟠 GAP

An implemented feature has a functional hole or an interaction that can produce incorrect behavior, but the impact is not an immediate system-wide blocker.

### 🔴 BLOCKER

Any issue that can cause:

- cross-workspace data exposure
- unauthorized financial mutation
- double counting / double spending of money
- incorrect financial settlement
- serious transaction integrity failure
- ledger/financial truth divergence
- production-critical security failure

must block final closure until fixed.

---

# 15. Working Rules During Implementation

1. Do not fix unrelated Accounts or Project Settings work during this closure.
2. Do not redesign the architecture unless the current contract cannot safely close the issue.
3. Prefer extending existing canonical services over creating duplicate financial engines.
4. Preserve immutable financial facts.
5. Preserve ledger immutability and idempotency.
6. Preserve workspace isolation at both application and database layers.
7. Every financial fix gets a regression test.
8. Every schema change gets migration validation.
9. Every meaningful code change gets CI verification.
10. Never report CI as green without checking the actual current run.
11. Never call the project production-ready merely because CI is green.
12. Never use an old branch/commit as current production truth.
13. After fixing a blocker, re-check neighboring interactions because financial bugs frequently cross service boundaries.
14. Final closure requires a fresh audit, not a checklist-only sign-off.

---

# 16. Current Known Closure Queue

The starting queue for this document is:

| ID | Area | Severity | Closure Action | Status |
|---|---|---:|---|---|
| P0-A | RLS / multi-tenancy | 🔴 | Complete policies for all workspace-owned tables + real restricted-role validation | OPEN |
| P0-B | Refund × Allocation × AdvanceCredit | 🔴 | Make payment capacity refund-aware and concurrency-safe | OPEN |
| P0-C | Dashboard financial truth | 🔴 | Align dashboard with canonical financial position | OPEN |
| P1.1 | Occupancy concurrency | 🟠 | Strengthen overlap/capacity guarantees | OPEN |
| P1.2 | Adjustment zero-receivable semantics | 🟠 | Define and enforce explicit status semantics | OPEN |
| P1.3 | Recurring financial bypass surfaces | 🟡 | Harden internal bypass boundaries | OPEN |
| P1.4 | Final settlement semantics | 🟡 | Document and test balance direction | OPEN |
| P1.5 | Payment reporting semantics | 🟡 | Clarify invoice-linked vs advance receipt reporting | OPEN |
| P1.6 | SubUnit lifecycle | 🟡 | Strengthen occupancy interaction protections | OPEN |
| P2.1 | Repository hygiene | 🟡 | Remove tracked `__pycache__` / `.pyc` artifacts | OPEN |
| P2.2 | Production security settings | 🟡 | Fresh production configuration audit | OPEN |
| P2.3 | Authorization hardening | 🟡 | Mutation endpoint/service-layer review | OPEN |
| RC | Regression suite | — | Expand interaction/security/failure tests | OPEN |
| VAL | Restricted DB role | 🔴 gate | Validate RLS without BYPASSRLS | OPEN |
| FINAL | Deep re-audit | 🔴 gate | Fresh current-branch audit | OPEN |
| FREEZE | Production baseline | 🔒 gate | Freeze only after all gates pass | OPEN |

---

# 17. Execution Start Point

The first implementation milestone after this document is locked is:

> **P0-A — RLS / Multi-Tenant Isolation Closure**

Execution order inside P0-A:

```text
1. Inventory current workspace-owned models/tables
2. Inventory current RLS enable/force state
3. Inventory current policies
4. Build table → policy coverage matrix
5. Identify direct-workspace vs relationship-derived policy requirements
6. Fix policy gaps
7. Add/strengthen RLS regression tests
8. Validate pure advance payment under RLS
9. Validate cross-workspace financial/KYC/application/ledger isolation
10. Validate with restricted PostgreSQL role
11. Run full CI
12. Record P0-A checkpoint
```

Only after P0-A passes should implementation move to **P0-B**.

---

# 18. Closure Principle

The final goal is not merely:

```text
CI = GREEN
```

The final goal is:

```text
Implemented functionality
        +
Correct domain contracts
        +
Workspace isolation
        +
Database RLS
        +
Financial integrity
        +
Transactional safety
        +
Regression coverage
        +
Real restricted-role validation
        +
Fresh final audit
        =
Reliable production baseline
```

This document is the locked execution roadmap for reaching that baseline on `production-branch`.
