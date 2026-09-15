# AjnihaStay — Leasing Lifecycle Contract

**Status:** P1.5 architectural clarification

## Contractual authority

`Lease` remains the contractual anchor for a tenancy relationship and remains linked to the authoritative `Occupancy`.

`LeaseContractVersion` stores immutable contractual-period snapshots. A lease may have multiple versions forming a predecessor/successor chain.

The **latest contract version by highest `version_number` is the current contractual version** for that Lease. Historical versions remain immutable and must never be rewritten to represent a later renewal.

Renewal therefore creates a successor `LeaseContractVersion`; it does not replace or mutate the original contractual history and does not become financial authority.

## Lifecycle mutation authority

The following mutations must go through their canonical services:

- Lease status: `lease_service`, `expiry_service`, `termination_service`, `cancellation_service`
- Notice status: `notice_service`
- Renewal lifecycle: `renewal_service`
- Lifecycle history: `append_lifecycle_event`
- Contract versions: creation only through the controlled leasing/renewal flow

Direct model saves and bulk queryset updates are defensive backstops and must not be used as alternate business workflows.

## Audit and immutability

Confirmed renewals, contract versions and lifecycle events are immutable. Notice status transitions are service-controlled. Renewal cancellation is recorded as a lifecycle event and is idempotent.

Workspace membership/RBAC and RLS remain the tenant-isolation boundaries. Leasing does not become financial authority; financial truth remains `Occupancy → Charge → Invoice → Payment`.
