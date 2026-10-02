# P4 — Property Ownership Assignment Boundary

Status: FROZEN / GREEN

## Architecture

Workspace ownership and Property ownership are separate concepts.

```
Workspace
  owner = Workspace Owner

Members
  owner / admin / manager / viewer

Property
  workspace = Workspace
  owner = explicitly selected active Workspace member
```

The actor creating a Property does not automatically become its owner.

Example:

```
Workspace owner: Saif

Saif  -> owner
Ali   -> admin
Rahul -> manager
Aman  -> viewer

Rahul creates Property A
Property A.owner = Saif
Property A.workspace = Saif's Workspace
```

## Frozen invariants

1. `Property.workspace` remains the tenant boundary.
2. `Property.owner` is a real business ownership field.
3. Property owner must be an active Membership of the same Workspace.
4. Property creator/actor and Property owner may be different users.
5. Property mutation authority remains owner/admin/manager.
6. Viewer cannot create a Property.
7. Canonical `create_property()` requires an explicit `owner`.
8. Direct Property mutation remains blocked by the P1 mutation boundary.
9. Workspace owner/provisioning architecture is unchanged.
10. Workspace RLS architecture is unchanged.
11. Existing Property rows are not silently rewritten.
12. P4 covers creation-time ownership assignment only.
13. Ownership transfer/change is intentionally deferred to a separate future checkpoint.

## Implementation

### Production files

- `properties/services.py`
  - validates mutation actor
  - validates explicit Property owner
  - validates active same-workspace Membership
  - persists selected owner rather than creator

- `properties/serializers.py`
  - `owner` is a writable `PrimaryKeyRelatedField`
  - inactive users are excluded from serializer input
  - service remains authoritative for workspace membership validation

- `unit/views.py`
  - passes `request.user` to the actor-aware Unit/SubUnit mutation services introduced by P3

### Tests

- `properties/tests/test_mutation_boundary.py`
  - updated fixtures for explicit owner
  - creator-vs-owner behavior
  - cross-workspace owner rejection
  - inactive owner rejection
  - missing owner rejection
  - viewer rejection

- `unit/tests/test_mutation_boundary.py`
  - updated Property fixtures for the P3/P4 service contract

## Database / migration decision

No schema migration is required for P4.

The existing `Property.owner` ForeignKey already represents the required ownership relationship. Existing data is preserved.

## Verification

CI run #1366:
- migrations: GREEN
- workspace RLS setup: GREEN
- Django test suite: GREEN
- Django system checks: GREEN
- total tests: 165

P4 is frozen as a reliable baseline.
