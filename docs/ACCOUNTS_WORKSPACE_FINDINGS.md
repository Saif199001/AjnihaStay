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

### Audit objective

Determine exactly which Membership mutations are canonical service operations and which direct ORM paths can bypass authorization, ownership protection, lifecycle rules, or future audit/event requirements.

The audit must explicitly inspect:
- `Membership.save()`
- `Membership.objects.update()`
- `Membership.objects.bulk_update()`
- Membership deletion
- role changes
- `is_active` changes
- workspace reassignment
- owner-role assignment
- direct Membership creation
- admin mutation paths
- serializer/API mutation paths
- interactions with the W1 owner-invariant triggers

### Important design constraint

W2 must **not** blindly block every direct Membership write. Legitimate internal creation and controlled maintenance may exist. The correction must establish a precise mutation authority boundary while preserving W1's authoritative owner invariant.

### Acceptance criteria

Fresh tests must establish, at minimum:
- owner role cannot be assigned through ordinary member-management paths;
- owner cannot be deactivated through ordinary member-management paths;
- unauthorized role changes are rejected;
- unsupported direct/bulk mutation cannot bypass protected membership rules;
- workspace reassignment cannot silently create cross-workspace corruption;
- ownership transfer remains the supported owner-transition mechanism;
- valid service-driven membership lifecycle operations continue to work.

**Current checkpoint:** A1 FROZEN → W1 FROZEN → **W2 FROZEN — GREEN** → W3 OPEN

---

## 4. Workspace — W3: Permission Exception Boundary

**Severity:** P1  
**Status:** FROZEN — GREEN

### Confirmed production finding

`workspaces/permissions.py` currently catches broad `Exception` in two permission-boundary locations:

1. `get_workspace_for_request(request)` is wrapped in `except Exception: return False`.
2. `set_workspace_context(workspace.id)` is wrapped in `except Exception: return False`.

This can convert unexpected application/database failures into an ordinary permission denial instead of allowing the failure to remain observable.

### W3 target

Catch only expected domain/request exceptions that represent an unavailable workspace context or authorization failure. Unexpected database, configuration, programming, or infrastructure exceptions must propagate normally.

The correction must preserve active workspace membership enforcement, role hierarchy enforcement, RLS workspace context setup, DRF permission semantics, and workspace isolation.

### Fresh test requirement

Fresh W3 tests must prove expected workspace/authentication/authorization exceptions remain handled, while unexpected exceptions from workspace resolution and `set_workspace_context()` are not swallowed.

**Current checkpoint:** A1 FROZEN → W1 FROZEN → W2 FROZEN — GREEN → **W3 FROZEN — GREEN** → W4 OPEN

---

## 5. Workspace — W4: API Error Contract

**Severity:** P2  
**Status:** IMPLEMENTED — VERIFICATION PENDING

Target contract:
- 401 — missing/invalid authentication
- 403 — authenticated but unauthorized
- 400 — invalid request/workspace selection
- unexpected failures — normal observable server error

Fresh tests required for affected endpoints.

---

## 6. Workspace — W5: Workspace Lifecycle Mutation Boundary

**Severity:** P2  
**Status:** OPEN

Keep authorization-sensitive lifecycle transitions behind canonical services, including:
- ownership transfer;
- member role transitions;
- member activation/deactivation;
- workspace archival;
- other tenancy/authorization-sensitive state transitions.

---

## 7. Checkpoint Dependency Order

1. **A1 — Account State Mutation Boundary — FROZEN**
2. **W1 — Workspace Owner Invariant — FROZEN**
3. **W2 — Membership Mutation Boundary — FROZEN**
4. **W3 — Permission Exception Boundary — CURRENT**
5. **W4 — API Error Contract**
6. **W5 — Workspace Lifecycle Mutation Boundary**

Reason:
- W1 establishes authoritative ownership consistency.
- W2 must preserve W1 while defining membership mutation authority.
- W3/W4 harden request and authorization contracts.
- W5 consolidates the final lifecycle mutation boundary.

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
| W4 | API error contract | P2 | OPEN — AUDIT IN PROGRESS |
| W5 | Workspace lifecycle boundary | P2 | OPEN |

### W4 implementation record

Production correction applied:
- `workspaces/api.py` now lets DRF preserve the native 401/403/400 exception contract instead of manually remapping authentication, authorization, and validation exceptions.
- `workspaces/services.py` now raises DRF `PermissionDenied` for ownership authorization failures in ownership transfer and workspace archival.
- Unexpected exceptions are not converted into client-facing 400/403 responses.

Fresh test suite:
- `workspaces/test_api_error_contract_production.py`

Implementation commits:
- `f30630b3d3da26d046c9f965441fa21e0fa74b96` — API error status semantics
- `3f3a687062c468b0943d679c3cc9c03bbf3fcc56` — authorization exception semantics
- `de4ef99b655d5622386d770135d16a347ace466f` — fresh W4 tests

**W4 checkpoint: IMPLEMENTED — VERIFICATION PENDING.**

**Current active checkpoint: W4 — API Error Contract.**


---

## 11. W2 Implementation Record

**Status:** FROZEN — GREEN.

### Production boundary

Membership mutation is now protected by a private controlled mutation context.

Protected application-level operations:
- Membership creation
- role changes
- active/inactive changes
- workspace reassignment
- user reassignment
- direct deletion
- QuerySet `update()`
- QuerySet `bulk_update()`
- QuerySet `bulk_create()`

Canonical service paths remain:
- `add_member()`
- `change_member_role()`
- `deactivate_member()`
- `transfer_workspace_ownership()`

The signup provisioning path uses the same private mutation context for the initial owner Membership.

### Service hardening

Membership management services now:
- lock the Workspace before membership mutation;
- reload and lock the actor Membership before authorization;
- lock the target Membership where applicable;
- perform state mutation only inside the controlled membership mutation context.

The W1 ownership-transfer flow remains the canonical owner transition and continues to use the existing owner-invariant database protection.

### Fresh tests

New suite:
- `workspaces/test_membership_mutation_boundary_production.py`

Coverage includes:
- direct creation;
- direct role/state/workspace/user mutation;
- QuerySet update;
- bulk update;
- bulk create;
- QuerySet delete;
- instance delete;
- valid service mutations;
- owner-role boundary;
- stale admin actor;
- W1 ownership-transfer regression.

### W2 verification and freeze

CI #1312 on `production-branch` was verified GREEN for commit `71a614bd41caf82839db88a865363aafbf14229a`.

The GitHub Actions UI showed Workflow `Django CI`, Run `#1312`, Status Success / GREEN, Branch `production-branch`, and the same commit.

**W2 checkpoint: FROZEN — GREEN.**

---

## 12. W3 Audit + Freeze Record

**Status:** FROZEN — GREEN.

Production correction narrowed the permission exception boundary in `workspaces/permissions.py` to the deliberate DRF exceptions:
- `NotAuthenticated`
- `PermissionDenied`
- `ValidationError`

Unexpected exceptions from workspace resolution and `set_workspace_context()` now propagate instead of being converted into permission denial.

Fresh test suite:
- `workspaces/test_permission_exception_boundary_production.py`

Implementation / verification:
- `257ab7400bfddd6d71c10e6229b5cdf52715a694` — production correction
- `33acd6cce28376dcd27df8df230c4719f6572b01` — fresh W3 tests
- CI #1314 — GREEN on `257ab7400bfddd6d71c10e6229b5cdf52715a694`
- CI #1315 — GREEN on `33acd6cce28376dcd27df8df230c4719f6572b01`

**W3 checkpoint: FROZEN — GREEN.**

## 13. W4 Audit Record

**Status:** AUDIT IN PROGRESS.

Initial production-code audit scope:
- `workspaces/api.py`
- `workspaces/membership_api.py`
- `workspaces/serializers.py`
- `workspaces/context.py`
- workspace URL contracts
- DRF authentication/permission configuration

Confirmed W4 focus:
- distinguish HTTP 401 authentication failures from HTTP 403 authorization failures;
- distinguish HTTP 400 validation/workspace-selection failures from authorization failures;
- avoid broad/manual exception remapping that changes the intended DRF status contract;
- preserve unexpected server failures as observable 5xx errors.

No W4 production correction has been applied yet.

**Current active checkpoint: W4 — API Error Contract.**
