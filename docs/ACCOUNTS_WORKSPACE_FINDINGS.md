# Accounts + Workspace — Production Code Findings / Correction Notes

**Repository:** `Saif199001/AjnihaStay`  
**Branch:** `production-branch`  
**Document status:** ACTIVE WORKING REFERENCE  
**Purpose:** This document records confirmed production-code findings, frozen checkpoints, and correction work for the Accounts + Workspace audit.

> **Workflow rule**
>
> Production code is the source of truth. Legacy tests/old CI failures are not used as the specification. A checkpoint is frozen only after production corrections, fresh tests, database behavior, and GREEN verification are complete.

---

## 1. Accounts — A1: Account State Mutation Boundary

**Severity:** P1  
**Status:** FROZEN — GREEN

Sensitive account-state fields:
- `User.is_active`
- `User.email_verified`
- `User.email_verified_at`

Canonical services:
- `set_account_active()`
- `verify_user_email()`

Implemented protection:
- `User.save()` blocks unauthorized sensitive-state changes.
- `UserQuerySet.update()` blocks sensitive-field bulk updates.
- `UserQuerySet.bulk_update()` blocks sensitive-field bulk updates.
- Canonical services use a private controlled mutation context.
- Deactivation continues to revoke outstanding JWT tokens.
- Email verification keeps state/timestamp consistent.

Fresh test suite:
- `accounts/test_accounts_production.py`

### A1 verification
CI #1296 on `production-branch` was verified GREEN at commit `77978c8ecbe8ca39420cda5477fb7cd05e5212d4`.

**A1 checkpoint: FROZEN.**

---

## 2. Workspace — W1: Workspace Owner Invariant

**Severity:** P1  
**Status:** FROZEN — GREEN

### Authoritative invariant

For every active workspace:

```
Workspace.owner
    ==
the User represented by
exactly one active Membership with role="owner"
```

### Production corrections

1. **Workspace INSERT invariant**
   - Added deferred database constraint trigger covering Workspace INSERT and owner changes.
   - This closes the gap where a Workspace could otherwise be created without a matching owner Membership.

2. **Ownership transfer freshness**
   - `transfer_workspace_ownership()` now locks and reloads the Workspace first.
   - The actor Membership is reloaded under lock before authorization is checked.
   - Current owner and target Membership rows are locked before transition.
   - Ownership transition remains atomic.

### Implementation commits

- `b2f7ab2f07dcfe2795544ade2b365d63ac1ff812` — workspace owner INSERT invariant
- `35c34e23fe874bffbfe3b85237713da38e31f2b9` — fresh actor membership before ownership transfer
- `95ee7897a2b05636f5bf04c010241babdf6f77aa` — W1 fresh production tests
- `66da5b2755c9ac48f2e417055b0e0560452e8afc` — tightened W1 fixtures
- `211c1a0f172112e4031d06b088b1ef9571c94687` — corrected DRF ValidationError assertion

Fresh test suite:
- `workspaces/test_workspace_owner_invariant_production.py`

### W1 verification

The latest `production-branch` CI was reported GREEN after the final W1 test correction.

Covered behavior includes:
- valid owner Membership;
- missing/wrong owner Membership;
- duplicate active owners;
- owner deactivation/deletion/role mutation;
- inconsistent `Workspace.owner`;
- valid ownership transfer;
- stale non-owner actor rejection.

**W1 checkpoint: FROZEN.**

---

## 3. Workspace — W2: Membership Mutation Boundary

**Severity:** P1  
**Status:** FROZEN — GREEN

### Scope

Primary production areas:
- `workspaces/models.py`
- `workspaces/services.py`
- `workspaces/api.py`
- `workspaces/membership_api.py`
- `workspaces/admin.py`

Canonical membership operations include:
- `add_member()`
- `change_member_role()`
- `deactivate_member()`
- `transfer_workspace_ownership()`

### Acceptance criteria

Fresh tests establish:
- owner role cannot be assigned through ordinary member-management paths;
- owner cannot be deactivated through ordinary member-management paths;
- unauthorized role changes are rejected;
- unsupported direct/bulk mutation cannot bypass protected membership rules;
- workspace reassignment cannot silently create cross-workspace corruption;
- ownership transfer remains the supported owner-transition mechanism;
- valid service-driven membership lifecycle operations continue to work.

### W2 verification and freeze

CI #1312 on `production-branch` was verified GREEN for commit `71a614bd41caf82839db88a865363aafbf14229a`.

**W2 checkpoint: FROZEN — GREEN.**

---

## 4. Workspace — W3: Permission Exception Boundary

**Severity:** P1  
**Status:** FROZEN — GREEN

Production correction narrowed the permission exception boundary in `workspaces/permissions.py` to deliberate DRF exceptions:
- `NotAuthenticated`
- `PermissionDenied`
- `ValidationError`

Unexpected exceptions from workspace resolution and `set_workspace_context()` now propagate instead of being converted into permission denial.

Fresh test suite:
- `workspaces/test_permission_exception_boundary_production.py`

Implementation / verification:
- `257ab7400bfddd6d71c10e6229b5cdf52715a694` — production correction
- `33acd6cce28376dcd27df8df230c4719f6572b01` — fresh W3 tests
- CI #1314 — GREEN
- CI #1315 — GREEN

**W3 checkpoint: FROZEN — GREEN.**

---

## 5. Workspace — W4: API Error Contract

**Severity:** P2  
**Status:** FROZEN — GREEN

### Target contract

- **401** — missing/invalid authentication
- **403** — authenticated but unauthorized
- **400** — invalid request/workspace selection
- **unexpected failures** — remain observable as server errors rather than being remapped into ordinary client errors

### Production corrections

- `workspaces/api.py` preserves native DRF exception semantics instead of manually remapping authentication, authorization, and validation failures.
- `workspaces/services.py` uses DRF `PermissionDenied` for authorization failures in ownership transfer and workspace archival.
- Unexpected exceptions are not converted into client-facing 400/403 responses.

### Fresh test suite

- `workspaces/test_api_error_contract_production.py`

Coverage includes:
- unauthenticated access → 401;
- authenticated non-member access → 403;
- missing workspace selection → 400;
- inaccessible workspace selection → 403;
- validation failure → 400;
- unauthorized workspace update → 403;
- unauthorized ownership transfer → 403;
- invalid transfer target → 400;
- unauthorized archive → 403;
- unexpected service failure propagates.

### Implementation and verification record

- `f30630b3d3da26d046c9f965441fa21e0fa74b96` — API error status semantics
- `3f3a687062c468b0943d679c3cc9c03bbf3fcc56` — authorization exception semantics
- `de4ef99b655d5622386d770135d16a347ace466f` — fresh W4 tests
- `b8083a5d57cec79b5e04121bca1c6870900d45c9` — W1 test aligned with W4 permission semantics
- `2fac2cd26b407151af95af3017aca48d2b7b3063` — W4 response-shape assertions corrected
- `3d61645a17fba49ccde7f91954475506dea176fd` — model/service permission exception classes separated

**CI #1323 on `production-branch` was verified GREEN** for commit `3d61645a17fba49ccde7f91954475506dea176fd`.

**W4 checkpoint: FROZEN — GREEN.**

---

## 6. Workspace — W5: Workspace Lifecycle Mutation Boundary

**Severity:** P2  
**Status:** FROZEN — GREEN

W5 has completed production correction, fresh-test verification, and CI verification.

### Scope

Audit authorization-sensitive workspace lifecycle transitions, including:
- workspace archival;
- ownership transfer lifecycle;
- member role transitions;
- member activation/deactivation;
- workspace state changes;
- stale actor authorization during lifecycle mutations;
- direct ORM bypasses of lifecycle services;
- concurrency/locking semantics;
- API/admin mutation paths;
- interactions with W1 owner invariant and W2 membership mutation boundary.

### W5 objective

Establish one clear canonical mutation boundary for workspace lifecycle state while preserving:
- workspace isolation;
- W1 owner invariant;
- W2 membership mutation boundary;
- W3 permission exception behavior;
- W4 HTTP 401/403/400 contract.

**Current active checkpoint: W5 — Workspace Lifecycle Mutation Boundary.**

### W5 production correction record

Implemented:
- Added a controlled Workspace mutation context and ORM mutation boundary for lifecycle fields.
- Direct Workspace lifecycle `save()`, QuerySet `update()`, `bulk_update()`, instance `delete()`, and QuerySet `delete()` are blocked outside the canonical lifecycle boundary.
- `update_workspace()` now locks the Workspace before authorization and reloads the actor Membership under lock.
- `archive_workspace()` now locks the Workspace and reloads the actor Membership before owner authorization.
- `transfer_workspace_ownership()` now routes the Workspace.owner mutation through the controlled Workspace mutation context while preserving W1/W2 behavior.
- Workspace Admin add/change/delete mutations are disabled.

Fresh test suite:
- `workspaces/test_workspace_lifecycle_mutation_boundary_production.py`

Implementation commits:
- `4c80d9c16b3c563b2fd361d0b539d0b61b95694c` — Workspace ORM lifecycle mutation boundary
- `670f3af17359c916c2e2d00eacdf96efabc07870` — fresh actor authorization for lifecycle services
- `686dcd7a79cba622494b5473b11ff257825c88ce` — Workspace Admin lifecycle boundary
- `e064a6308d65b977dbfe0cfea7c06826b4ec323b` — fresh W5 production tests

**CI #1330 on `production-branch` was verified GREEN** for commit `a96637c40aa7ab3d43c3a7e27d4866a14395f3fe`.

**W5 checkpoint: FROZEN — GREEN.**

---

## 7. Checkpoint Dependency Order

1. **A1 — Account State Mutation Boundary — FROZEN**
2. **W1 — Workspace Owner Invariant — FROZEN**
3. **W2 — Membership Mutation Boundary — FROZEN**
4. **W3 — Permission Exception Boundary — FROZEN**
5. **W4 — API Error Contract — FROZEN**
6. **W5 — Workspace Lifecycle Mutation Boundary — FROZEN**

Reason:
- W1 establishes authoritative ownership consistency.
- W2 establishes membership mutation authority while preserving W1.
- W3 hardens request/permission exception behavior.
- W4 establishes the HTTP error contract.
- W5 consolidates authorization-sensitive workspace lifecycle mutation boundaries.

---

## 8. Fresh Test Requirement

Only fresh production tests are used for these corrections.

Workspace fresh tests must cover:
- owner invariant;
- ownership transfer;
- membership role lifecycle;
- membership deactivation;
- permission exception behavior;
- HTTP 401/403/400 contract;
- workspace lifecycle mutation boundaries.

Legacy tests are not the specification.

---

## 9. Freeze Condition

A checkpoint may be frozen only when:
1. production correction is complete;
2. fresh tests cover the corrected contract;
3. relevant tests are GREEN;
4. migration/database behavior is verified;
5. no known P1 finding remains open for that checkpoint;
6. the final production architecture is documented.

---

## 10. Current Checkpoint Status

| Checkpoint | Area | Severity | Status |
|---|---|---:|---|
| A1 | Accounts state mutation boundary | P1 | FROZEN — GREEN |
| W1 | Workspace owner invariant | P1 | FROZEN — GREEN |
| W2 | Membership mutation boundary | P1 | FROZEN — GREEN |
| W3 | Permission exception boundary | P1 | FROZEN — GREEN |
| W4 | API error contract | P2 | FROZEN — GREEN |
| W5 | Workspace lifecycle boundary | P2 | FROZEN — GREEN |

---

## 11. W2 Implementation Record

**Status:** FROZEN — GREEN.

Membership mutation is protected by a private controlled mutation context.

Canonical service paths:
- `add_member()`
- `change_member_role()`
- `deactivate_member()`
- `transfer_workspace_ownership()`

Protected application-level operations include:
- Membership creation;
- role changes;
- active/inactive changes;
- workspace reassignment;
- user reassignment;
- direct deletion;
- QuerySet `update()`;
- QuerySet `bulk_update()`;
- QuerySet `bulk_create()`.

Service paths lock the Workspace, reload and lock the actor Membership, lock target Memberships where applicable, and mutate only inside the controlled context.

Fresh suite:
- `workspaces/test_membership_mutation_boundary_production.py`

CI #1312 was verified GREEN.

---

## 12. W3 Audit + Freeze Record

**Status:** FROZEN — GREEN.

The permission boundary now catches only expected DRF exceptions and allows unexpected failures to propagate.

Fresh suite:
- `workspaces/test_permission_exception_boundary_production.py`

CI #1314 and #1315 were verified GREEN.

---

## 13. W4 Audit + Freeze Record

**Status:** FROZEN — GREEN.

W4 established the HTTP error contract across the affected workspace APIs:
- 401 for unauthenticated access;
- 403 for authenticated but unauthorized access;
- 400 for validation/workspace-selection errors;
- unexpected failures remain observable rather than being converted into ordinary client errors.

Fresh suite:
- `workspaces/test_api_error_contract_production.py`

Final verification:
- **CI #1323 — GREEN**
- commit: `3d61645a17fba49ccde7f91954475506dea176fd`
- branch: `production-branch`

**W4 checkpoint: FROZEN — GREEN.**

---

## 14. W5 Freeze Record

**Status:** FROZEN — GREEN.

W5 completed its production-code audit, correction implementation, fresh production test suite, database/invariant verification, and CI verification.

Final verification:
- **CI #1330 — GREEN**
- commit: `a96637c40aa7ab3d43c3a7e27d4866a14395f3fe`
- branch: `production-branch`

Frozen scope:
- Workspace lifecycle mutation boundary;
- stale actor authorization protection;
- direct ORM lifecycle mutation protection;
- Workspace Admin lifecycle mutation boundary;
- preservation of W1 owner invariant;
- preservation of W2 membership mutation boundary;
- preservation of W3 permission exception behavior;
- preservation of W4 HTTP error semantics.

**W5 checkpoint: FROZEN — GREEN.**

**Next checkpoint: W6 — production-code audit required before implementation.**

## 15. Accounts + Workspace Final Closure — C1–C5

**Closure status: FROZEN — GREEN**

The final cross-boundary production audit of Accounts + Workspace is complete on
`production-branch`. The closure findings C1–C5 were reviewed against the
production code, fresh tests, database invariants, and the locked Blueprint.

### C1 — Active Workspace Owner Deactivation

**Status: FROZEN — GREEN**

Finding:
- An active Workspace could otherwise be stranded if its owner account were deactivated.

Correction:
- `set_account_active()` now checks for active Workspaces owned by the account before deactivation.
- Ownership must be transferred or the Workspace archived before the owner account can be deactivated.
- Account-state mutation remains behind the A1 canonical mutation boundary.

Implementation:
- `1f900b129e38ae80de7e1b4a4a0d9f3b14049631` — protect active workspace owners from deactivation.

Fresh coverage:
- owner with one active Workspace is blocked;
- owner with multiple active Workspaces is blocked;
- non-owner/member deactivation remains allowed;
- owner can be deactivated after all owned Workspaces are archived.

Verification:
- **CI #1332 — GREEN**
- branch: `production-branch`

**C1 checkpoint: FROZEN — GREEN.**

### C2 — Permission ↔ HTTP Status Reconciliation

**Status: FROZEN — GREEN**

Finding:
- The workspace permission class was converting deliberate authentication/authorization/validation exceptions into `False`, which could change the intended HTTP semantics.

Correction:
- `HasWorkspaceMembership` now preserves the deliberate DRF exception flow from workspace resolution.
- Role permissions continue to use boolean authorization checks.
- Unexpected failures remain observable.

Resulting contract:
- 401 — unauthenticated;
- 403 — authenticated but unauthorized;
- 400 — validation/workspace-selection errors.

Implementation:
- `730f36df68a351341ae4a4ff86ed15351a794e70` — preserve permission exception HTTP semantics.
- `81fef16ec0247ed19872f9e1303757fba80a70d5` — align fresh permission tests with C2 semantics.

Verification:
- **C2 — GREEN**
- fresh W3/C2 permission tests pass on `production-branch`.

**C2 checkpoint: FROZEN — GREEN.**

### C3 — Platform Admin Authority Boundary

**Status: FROZEN — GREEN**

Finding:
- Platform privilege fields in Django Admin required an explicit platform-authority boundary separate from Workspace RBAC.

Correction:
- Non-superusers cannot modify `is_staff`, `is_superuser`, `groups`, or `user_permissions`.
- Superusers retain platform-level privilege authority.
- Account activation continues through the canonical account service.
- Workspace Admin remains a separate tenant/workspace role.

Implementation:
- `baf8f0ffd2ca0f780d55a5f296f41decd49395d3` — platform admin authority boundary.
- `ed0c6be77e5c0ca886a25706a767bdafa7ebf528` — final fresh C3 test coverage.

Verification:
- **CI #1339 — GREEN**
- branch: `production-branch`

**C3 checkpoint: FROZEN — GREEN.**

### C4 — Account Deletion Lifecycle

**Status: FROZEN — GREEN**

Finding:
- Direct User deletion was an uncontrolled lifecycle path and could otherwise cascade Membership rows.

Correction:
- `User.delete()` and `UserQuerySet.delete()` are blocked in the normal application lifecycle.
- Django User Admin deletion is disabled.
- Normal account closure remains soft deactivation through `set_account_active()`.
- No uncontrolled hard-delete path is exposed.

Implementation:
- `cb2f2480226a387ce01a77a9a91340afa638bced` — account deletion lifecycle boundary.
- `13c2d50d6179b4ef01b003acba4b06f813e91ee4` — disable Admin account deletion.
- `8e007c2aaedae73fc18c9a7b473f0981853a4dd6` — final C4 fixture correction.

Verification:
- **CI #1343 — GREEN**
- branch: `production-branch`

**C4 checkpoint: FROZEN — GREEN.**

### C5 — Provisioning Authority

**Status: FROZEN — NO PRODUCTION CORRECTION REQUIRED**

Final production audit found no active provisioning defect.

Established architecture:

```
Platform administration
        ↓
Django Admin
        ↓
Platform-level account administration

SaaS signup
        ↓
create_user_account()
        ↓
User + Workspace + Owner Membership
        ↓
Workspace Owner
        ↓
Workspace Admin / Manager / Viewer
```

Important distinction:

- **Django Platform Admin** is not the same as **Workspace Admin**.
- A SaaS signup user receives the Workspace Owner role.
- The Owner manages Workspace Admin/Manager/Viewer memberships through the canonical workspace services.
- Django Admin is a platform authority and is not the SaaS tenant-membership workflow.
- A User account does not inherently require a Workspace; tenant provisioning is the separate User + Workspace + Owner Membership operation.
- `create_user_account()` remains the canonical SaaS signup provisioning path and is atomic.
- W1's deferred database invariant prevents a Workspace from persisting without the required matching active Owner Membership.

No production-code change was introduced for C5 because the audit found the existing architecture consistent with the Blueprint's separation of platform administration and customer workspace authorization.

**C5 checkpoint: FROZEN — GREEN / NO CORRECTION REQUIRED.**

---

## 16. Accounts + Workspace Final Architecture Freeze

The following boundaries are now treated as a **frozen production baseline**:

1. **A1 — Account State Mutation Boundary**
2. **W1 — Workspace Owner Invariant**
3. **W2 — Membership Mutation Boundary**
4. **W3 — Permission Exception Boundary**
5. **W4 — API Error Contract**
6. **W5 — Workspace Lifecycle Mutation Boundary**
7. **C1 — Active Workspace Owner Deactivation**
8. **C2 — Permission ↔ HTTP Status Reconciliation**
9. **C3 — Platform Admin Authority Boundary**
10. **C4 — Account Deletion Lifecycle**
11. **C5 — Provisioning Authority**

### Final invariants

- Workspace Owner ↔ active Owner Membership remains consistent.
- Membership lifecycle mutations use canonical workspace services.
- Workspace lifecycle mutations use canonical workspace services.
- Sensitive account-state mutations use canonical account services.
- Active Workspace owners cannot be deactivated.
- Normal account hard deletion is not an application lifecycle operation.
- Platform Admin authority is separate from Workspace RBAC.
- Workspace Admin is a tenant/workspace role, not Django Platform Admin.
- SaaS signup atomically provisions User + Workspace + Owner Membership.
- Workspace HTTP error semantics remain 401/403/400 as defined by the API contract.
- Unexpected application failures are not silently converted into ordinary permission/client errors.
- Workspace isolation and RLS architecture remain protected.
- Existing supported business workflows remain governed by the Blueprint's no-regression rule.

### Final verification baseline

The closure work was verified through the relevant fresh production test suites and GREEN CI checkpoints, including:

- A1 — CI #1296
- W1 — CI #1330 final W5-compatible verification
- W2 — CI #1312
- W3 — CI #1315
- W4 — CI #1323
- W5 — CI #1330
- C1 — CI #1332
- C2 — GREEN after final fresh-test correction
- C3 — CI #1339
- C4 — CI #1343

**Accounts + Workspace: FINAL FROZEN BASELINE 🔒**

Future work on later apps must treat these boundaries as established contracts. Reopening them is required only if a later app introduces a concrete cross-boundary regression or a new architectural requirement.

**Next step: move to the next application audit.**
