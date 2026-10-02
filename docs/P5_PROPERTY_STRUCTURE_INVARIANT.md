# P5 — Property Structure Invariant

Status: IMPLEMENTED / CI VERIFICATION PENDING

## Locked decision

`has_subunits` is a server-controlled structural property.

The client selects `property_type`; the system derives and enforces `has_subunits`.

| Property Type | has_subunits |
|---|---:|
| PG | true |
| Hostel | true |
| Shop | false |
| Flat | false |
| Office | false |
| Building | false |

## Invariants

1. `has_subunits` is not client-writable through `PropertySerializer`.
2. `create_property()` derives `has_subunits` from `property_type`.
3. The Property model rejects inconsistent `property_type` / `has_subunits` combinations.
4. The database enforces the same invariant with a CHECK constraint.
5. The migration validates existing rows before adding the constraint and does not silently rewrite data.
6. The mapping is centralized in `properties.models.SUBUNIT_PROPERTY_TYPES`.
7. P4 ownership behavior is unchanged.

## Implementation

- `properties/models.py` — centralized subunit-capable property types, model validation, and database CHECK constraint.
- `properties/serializers.py` — `has_subunits` is read-only.
- `properties/services.py` — reuses the model-level property structure mapping.
- `properties/migrations/0007_property_structure_invariant.py` — validates existing data and adds the CHECK constraint.
- `properties/tests/test_mutation_boundary.py` — mapping, serializer, model, and DB invariant tests.

## Scope boundary

This checkpoint does not introduce user-configurable custom structures.

If AjnihaStay later needs a property type whose unit/subunit structure is configurable, that should be designed as a separate architecture checkpoint rather than making `has_subunits` client-controlled.

## Verification

CI run 1372 is running against commit `79088f63d1c6bbb35725de1b7d9a15ccff93ee44`.

P5 remains open until CI completes successfully.
