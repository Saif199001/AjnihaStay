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
**Status:** OPEN — AUDIT STARTING

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

**Current checkpoint:** A1 FROZEN → W1 FROZEN → **W2 AUDIT IN PROGRESS**

---

## 4. Workspace — W3: Permission Exception Boundary

**Severity:** P1  
**Status:** OPEN

Replace broad `except Exception` handling in workspace permission checks with explicit expected exception handling. Unexpected application/database failures must remain observable.

---

## 5. Workspace — W4: API Error Contract

**Severity:** P2  
**Status:** OPEN

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
3. **W2 — Membership Mutation Boundary — CURRENT**
4. **W3 — Permission Exception Boundary**
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
| W2 | Membership mutation boundary | P1 | OPEN — AUDIT IN PROGRESS |
| W3 | Permission exception boundary | P1 | OPEN |
| W4 | API error contract | P2 | OPEN |
| W5 | Workspace lifecycle boundary | P2 | OPEN |

**Current active checkpoint: W2 — Membership Mutation Boundary.**
