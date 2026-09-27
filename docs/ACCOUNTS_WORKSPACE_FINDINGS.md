# Accounts + Workspace — Production Code Findings / Correction Notes

**Repository:** `Saif199001/AjnihaStay`  
**Branch:** `production-branch`  
**Document status:** AUDIT FINDINGS — CORRECTION PENDING  
**Purpose:** This document records the confirmed production-code findings from the fresh Accounts + Workspace audit. It is the working reference for the correction phase.

> **Important workflow rule**
>
> These findings were identified from the current production code. No correction is assumed to be complete until the production code is changed, fresh tests are added, and the relevant app is verified GREEN.
>
> Old CI failures and legacy tests are **not** the source of truth for these corrections.

---

## 1. Accounts — A1: Account State Mutation Boundary

**Severity:** P1  
**Status:** OPEN

### Affected production code

Primary files:

- `accounts/models.py`
- `accounts/services.py`
- `accounts/api.py`
- `accounts/admin.py`

Sensitive account-state fields:

- `User.is_active`
- `User.email_verified`
- `User.email_verified_at`

Canonical service functions already exist for important state changes:

- `set_account_active()`
- `verify_user_email()`

### Problem

The application has canonical service methods for sensitive account-state transitions, but the model itself does not make those fields intrinsically protected.

Therefore, another code path can potentially perform direct ORM mutation such as:

```python
user.is_active = False
user.save()
```

or:

```python
User.objects.filter(...).update(is_active=False)
```

without necessarily passing through the intended service-level transition logic.

This matters because account deactivation is not only a boolean change: the canonical deactivation path also revokes outstanding JWT tokens.

Similarly, email verification state should have one authoritative transition boundary.

### Required correction

Establish a clear canonical mutation boundary for sensitive account state.

Target:

- normal application code uses service functions;
- direct mutation paths that can bypass required security behavior are prevented or tightly controlled;
- deactivation continues to revoke outstanding tokens;
- email verification continues to update verification timestamp consistently;
- admin changes continue to use the canonical service.

### Acceptance criteria

- No supported application path can silently bypass required account-state transition logic.
- Deactivation always performs token revocation.
- Verification state remains internally consistent.
- Fresh production tests cover direct/bypass attempts where technically applicable.

---

## 2. Workspace — W1: Workspace Owner Invariant

**Severity:** P1  
**Status:** OPEN / AUTHORITATIVE ENFORCEMENT TO BE VERIFIED

### Affected production code

Primary files:

- `workspaces/models.py`
- `workspaces/services.py`
- workspace migrations

Important state:

- `Workspace.owner`
- `Membership.role`
- `Membership.is_active`

Canonical service:

- `transfer_workspace_ownership()`

### Required invariant

For every active workspace:

```
Workspace.owner
    ==
the User represented by
exactly one active Membership with role="owner"
```

### Problem

Ownership is represented in two places:

1. `Workspace.owner`
2. `Membership(role="owner", is_active=True)`

The service layer maintains this relationship during ownership transfer, but duplicated state requires authoritative protection against bypasses.

A direct ORM mutation, bulk update, migration/data repair, or future code path must not be able to leave these two sources of truth inconsistent.

### Required correction

Verify and, where necessary, strengthen the authoritative database/service enforcement so that:

- exactly one active owner membership exists;
- Workspace.owner points to that owner;
- ownership transfer is atomic;
- owner membership cannot be independently changed into an inconsistent state;
- direct/bulk ORM operations cannot create a supported inconsistent state.

### Important note

The audit identified the invariant as a production correctness requirement. The exact current migration/trigger implementation must be re-verified before treating the database layer as fully authoritative.

### Acceptance criteria

Fresh tests must prove:

- one active owner only;
- Workspace.owner matches the active owner membership;
- ownership transfer remains atomic;
- invalid owner states are rejected;
- bypass attempts are blocked at the appropriate layer.

---

## 3. Workspace — W2: Membership Mutation Boundary

**Severity:** P1  
**Status:** OPEN

### Affected production code

Primary files:

- `workspaces/models.py`
- `workspaces/services.py`
- `workspaces/api.py`
- `workspaces/membership_api.py`
- `workspaces/admin.py`

Canonical service operations include:

- `add_member()`
- `change_member_role()`
- `deactivate_member()`
- `transfer_workspace_ownership()`

### Problem

Membership lifecycle and RBAC state are intended to be controlled by service-layer rules.

However, Django ORM operations such as:

```python
Membership.objects.filter(...).update(...)
```

or:

```python
Membership.objects.bulk_update(...)
```

can bypass `save()`-based logic and service-level authorization.

This can potentially bypass:

- role restrictions;
- owner protection;
- active/inactive rules;
- workspace ownership invariants;
- future audit/event requirements.

### Required correction

Define and enforce the canonical membership mutation boundary.

The correction must distinguish between:

- safe administrative/query operations;
- supported lifecycle mutations;
- internal maintenance/data migrations;
- unsupported direct ORM mutation.

### Acceptance criteria

Fresh tests must cover at minimum:

- owner role cannot be assigned through normal member-management APIs;
- owner cannot be deactivated through normal member-management APIs;
- unauthorized role changes are rejected;
- inactive membership cannot be incorrectly reactivated through unsupported paths;
- ownership transfer remains the only supported owner-transition mechanism.

---

## 4. Workspace — W3: Permission Exception Boundary

**Severity:** P1  
**Status:** OPEN

### Affected production code

Primary file:

- `workspaces/permissions.py`

Relevant code:

```python
try:
    workspace, membership = get_workspace_for_request(request)
except Exception:
    return False
```

and:

```python
try:
    set_workspace_context(workspace.id)
except Exception:
    return False
```

### Problem

Broad `except Exception` handling hides unexpected programming, database, configuration, and infrastructure errors.

A permission class should distinguish:

- expected authentication/authorization failures;
- expected workspace-selection validation failures;
- actual application/infrastructure failures.

Returning `False` for every exception can turn a real defect into a generic permission denial and make diagnosis difficult.

### Required correction

Replace broad exception swallowing with explicit handling of expected exception types.

Unexpected exceptions must remain observable through normal Django/DRF error handling and logging.

### Acceptance criteria

- Expected authorization failures produce the intended permission response.
- Unexpected database/application errors are not silently converted into permission denial.
- Workspace context failures are handled explicitly.
- Fresh tests cover expected and unexpected exception paths.

---

## 5. Workspace — W4: API Error Contract

**Severity:** P2  
**Status:** OPEN

### Affected production code

Primary file:

- `workspaces/api.py`

Relevant endpoints include:

- workspace current
- workspace update
- ownership transfer
- workspace archive

### Problem

Some API handlers catch several different exception classes together and map them to the same HTTP response.

For example, the current-workspace endpoint catches:

- `NotAuthenticated`
- `PermissionDenied`
- `ValidationError`

and returns HTTP 403.

These conditions have different meanings:

- **401** — authentication is missing/invalid;
- **403** — authenticated user lacks permission;
- **400** — request/workspace selection is invalid.

Collapsing them weakens the API contract and makes client behavior less precise.

### Required correction

Normalize the API error contract:

| Condition | Target HTTP contract |
|---|---:|
| Missing/invalid authentication | 401 |
| Authenticated but unauthorized | 403 |
| Invalid request/workspace selection | 400 |
| Unexpected application failure | normal server error / observable failure |

Do not change business behavior merely to make tests pass; the API contract must reflect the actual domain semantics.

### Acceptance criteria

Fresh tests explicitly verify 401/403/400 behavior for the affected endpoints.

---

## 6. Workspace — W5: Workspace Lifecycle Mutation Boundary

**Severity:** P2  
**Status:** OPEN

### Affected production code

Primary file:

- `workspaces/services.py`

Important operations:

- `archive_workspace()`
- `transfer_workspace_ownership()`
- member lifecycle services
- workspace update service

### Problem

Workspace lifecycle and ownership/RBAC changes are security-sensitive domain operations.

The architecture already places important transitions in services, which is correct. The remaining issue is to make the service boundary explicit and ensure supported application paths do not bypass it through direct model/ORM mutation.

### Required correction

Keep the following behind canonical services:

- ownership transfer;
- member role transitions;
- member activation/deactivation;
- workspace archival;
- other lifecycle state transitions that affect authorization or tenancy.

Where necessary, add model/database protections against bypasses.

### Acceptance criteria

- API and admin paths use canonical services.
- Direct unsupported mutation cannot silently violate workspace lifecycle rules.
- Fresh tests cover lifecycle transition boundaries.

---

# 7. Finding Dependency Order

The corrections should be implemented in this order:

1. **A1 — Account State Mutation Boundary**
2. **W1 — Workspace Owner Invariant**
3. **W2 — Membership Mutation Boundary**
4. **W3 — Permission Exception Boundary**
5. **W4 — API Error Contract**
6. **W5 — Workspace Lifecycle Mutation Boundary**

Reason:

- W1 depends on the ownership model being authoritative.
- W2 must preserve W1.
- W3/W4 are request/authorization contract hardening.
- W5 consolidates the final lifecycle mutation boundary.

---

# 8. Fresh Test Requirement

After production correction:

### Accounts

Create/maintain only fresh production tests for the corrected behavior.

Required focus:

- account state transitions;
- token revocation;
- email verification state;
- direct mutation/bypass protection where applicable.

### Workspace

Create fresh production tests for:

- owner invariant;
- ownership transfer;
- membership role lifecycle;
- membership deactivation;
- permission exception behavior;
- HTTP 401/403/400 contract;
- workspace lifecycle mutation boundaries.

Legacy tests must not be used as the specification for these corrections.

---

# 9. Freeze Condition

Accounts + Workspace must **not** be marked FROZEN merely because code changes compile or an old CI suite passes.

The checkpoint can be frozen only when:

1. production code corrections are complete;
2. fresh tests cover the corrected contracts;
3. relevant tests are GREEN;
4. migration/database behavior is verified;
5. no known P1 finding remains open;
6. the final production architecture is documented.

---

## 10. Current Status

| Finding | Area | Severity | Status |
|---|---|---:|---|
| A1 | Accounts state mutation boundary | P1 | OPEN |
| W1 | Workspace owner invariant | P1 | OPEN |
| W2 | Membership mutation boundary | P1 | OPEN |
| W3 | Permission exception boundary | P1 | OPEN |
| W4 | API error contract | P2 | OPEN |
| W5 | Workspace lifecycle boundary | P2 | OPEN |

**Current checkpoint:** Accounts + Workspace = **AUDIT COMPLETE / CORRECTION PENDING**

**No correction is considered complete until verified by fresh production tests.**
