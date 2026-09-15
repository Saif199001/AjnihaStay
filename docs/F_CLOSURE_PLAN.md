# Financial Core F-Closure Plan

Status: LOCK CANDIDATE

## Scope

Close the remaining recurring-billing integrity gaps F5-F13 without weakening existing financial contracts.

F5 BillingSchedule uniqueness: at most one active recurring schedule per occupancy.
F6 Canonical recurring invoice integration: recurring invoice generation must use the canonical invoice transition and ledger path.
F7 Recurring billing orchestration: charge/invoice processing has one explicit atomic orchestration boundary.
F8 Scheduler/worker: deployment-time architecture only; no production worker runtime is introduced in this phase.
F9 Retry/idempotency: deterministic occurrence identity and safe replay semantics.
F10 Catch-up: missed periods are processed explicitly and deterministically, never implicitly skipped or duplicated.
F11 Checkout: schedules terminate safely when occupancy ends.
F12 Monthly anchor: monthly schedules preserve their original anchor day, including end-of-month behavior.
F13 Adversarial/concurrency suite: cover concurrent generation, rollback, isolation, retry and scheduler batch boundaries.

## F8 Deployment Contract

Production deployment will run a single recurring-billing worker/command against due schedules. The worker must invoke the canonical orchestration service, rely on database row locks and occurrence identities for concurrency safety, isolate failures per occurrence, emit structured logs/metrics, and support graceful shutdown/retry. Deployment configuration is intentionally deferred until production deployment.

## Invariants

- Financial state remains authoritative in domain services.
- Workspace isolation and RBAC/RLS remain mandatory.
- Existing partial, advance and arrears workflows remain unchanged.
- AI/automation never becomes financial truth.
- Scheduler/worker is an execution mechanism, not a second financial authority.
