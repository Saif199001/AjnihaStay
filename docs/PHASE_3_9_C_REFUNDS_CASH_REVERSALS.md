# Phase 3.9-C — Financial Refunds & Cash Reversal Events

**Status:** DRAFT — ARCHITECTURE REVIEWED 🔍  
**Version:** v1.0-draft  
**Date:** 2026-09-09  
**Branch:** `phase-3.9/credits-debits-adjustments`

## 1. Purpose

Phase 3.9-C introduces the architecture for **cash-return events** without redefining the existing receivable, payment-allocation, or advance-credit models.

The core distinction is:

- `Payment` = money received.
- `PaymentAllocation` = historical application of received money to an invoice.
- `AdvanceCredit` = prepaid money reserved for future settlement.
- `FinancialAdjustment` = receivable-side credit/debit/discount/waiver/write-off.
- `Refund` = money returned from a previously received payment.
- `RefundReversal` = a later event reversing a successful refund.

A refund is therefore **not** a credit adjustment and must not be represented by mutating or deleting the original payment.

## 2. Architectural Authority

The Phase 3 financial architecture remains authoritative:

`Business Event → Canonical Financial Service → Validated State Transition → Financial Record → Ledger/Reporting/Notifications`

Phase 3.9-C must preserve this boundary. API handlers, model `save()`, signals, and gateway callbacks must not become competing financial truth.

## 3. Proposed Domain Model

### 3.1 PaymentRefund

A `PaymentRefund` is an immutable financial event associated primarily with a `Payment`.

Candidate fields:

- `id`
- `workspace`
- `payment`
- `amount`
- `status`
- `reason`
- `reference`
- `idempotency_key`
- `requested_by`
- `created_at`
- `updated_at`
- future provider fields: `provider`, `provider_reference`, `provider_status`
- future failure metadata: `failure_reason`

The payment relationship is primary because one payment may span multiple invoices through allocations. Refunds are cash-side events, not invoice-side adjustments.

### 3.2 PaymentRefundReversal

A future `PaymentRefundReversal` should be a separate immutable event referencing the original successful refund.

It must not mutate the original refund into another state merely to erase history.

## 4. Refund State Machine

Initial core lifecycle:

`requested → processing → succeeded`

Failure path:

`requested/processing → failed`

Future reversal path:

`succeeded → reversed` via a separate reversal event.

Rules:

- A failed refund is not a completed cash-return event.
- A successful refund is permanent financial history.
- A refund reversal is a new financial event.
- Gateway/webhook status must pass through the canonical refund service.
- Provider-specific states must be mapped into the provider-neutral lifecycle.

## 5. Core Invariants

### 5.1 Positive Amount

`Refund.amount > 0`

### 5.2 Refund Capacity

For a payment:

`successful_refunds + active_refund_reservations <= refundable_payment_capacity`

The capacity must be calculated while holding the payment row lock.

The exact business definition of `refundable_payment_capacity` remains an architecture decision before implementation because captured/allocated payment semantics vary by business policy and future gateway integration.

### 5.3 Idempotency

Idempotency is workspace/payment scoped.

- Same key + same operation → return the existing refund.
- Same key + different operation → reject as conflict.
- Creation and capacity validation must be concurrency-safe.

The database remains the final uniqueness authority.

### 5.4 Immutability

The following historical records remain immutable:

- `Payment`
- `PaymentAllocation`
- `AdvanceCredit`
- `FinancialAdjustment`
- successful `PaymentRefund`

Refund processing status may transition only through the canonical refund service; original financial facts must not be silently rewritten.

## 6. PaymentAllocation Interaction

A refund must **not** automatically reduce or rewrite `PaymentAllocation`.

Example:

- Payment = ₹10,000
- Allocation = ₹10,000
- Refund = ₹2,000

The allocation remains a historical record of how the received payment was applied. The refund separately records that ₹2,000 was returned.

This deliberately leaves the eventual accounting/reconciliation treatment to the future ledger phase rather than creating hidden mutations in the current invoice model.

## 7. Advance Credit Boundary

Refunding or redeeming `AdvanceCredit` is explicitly outside the initial 3.9-C core.

`AdvanceCredit` represents prepaid capacity. Introducing refundable customer-wallet semantics would require a separate lifecycle for refundable balance, redemption, liability/accounting treatment, and reconciliation.

That capability remains deferred.

## 8. Invoice State Boundary

Phase 3.9-C must **not redefine `Invoice.status`**.

The current legacy state remains:

- `pending`
- `partial`
- `paid`

A refund is a cash-side event and does not automatically become an invoice credit adjustment.

The existing Phase 3.9-B canonical receivable position remains authoritative:

`Gross Receivable + Debit Adjustments - Reducing Adjustments = Adjusted Receivable`

`Adjusted Receivable - PaymentAllocations - AdvanceCreditApplications = Outstanding`

Phase 3.9-C additionally introduces the distinct concept:

`Net Cash Retained = Payments - Successful Refunds`

These quantities are intentionally not forced to be identical before the accounting/ledger phase.

## 9. Full / Partial / Multiple Refunds

The design supports:

- full refund,
- partial refund,
- multiple partial refunds,
- total refunds capped at the remaining refundable amount.

A payment may therefore have multiple refund records while preserving every individual cash event.

## 10. Multi-Invoice Payments

Because one `Payment` may be allocated across multiple invoices, the core refund entity references the payment rather than requiring a single invoice.

Optional invoice/allocation attribution may be added later for reconciliation and reporting, but it must not turn invoice allocation into the source of truth for cash refund capacity.

## 11. Concurrency

Refund creation is a financial mutation and must be transactionally serialized.

Candidate implementation boundary:

1. Begin atomic transaction.
2. Lock the workspace-scoped payment row with `select_for_update()`.
3. Re-check payment ownership/workspace.
4. Recalculate successful refunds and active reservations.
5. Validate remaining refundable capacity.
6. Resolve idempotency.
7. Create the refund event/reservation.
8. Commit.

Gateway processing must occur outside the database transaction where appropriate; the persisted state machine records the asynchronous outcome.

## 12. Authorization

Initial mutation authorization should remain aligned with the existing financial mutation boundary:

- owner
- admin
- manager

However, refund approval thresholds, dual control, or maker-checker workflows should be treated as a future explicit capability rather than invented inside the core service.

API authorization and service authorization must both be enforced.

## 13. API Boundary

The API should expose a dedicated refund endpoint rather than embedding refund behavior inside payment creation/update endpoints.

Candidate boundary:

`POST /api/payment-refunds/create/`

The API should:

- validate input shape,
- enforce authentication/workspace context,
- enforce manager-level authorization,
- pass the canonical command to the refund service,
- return the persisted refund state and relevant payment refund summary.

It must not perform financial mutation logic itself.

## 14. Gateway Integration Boundary

The core model/service must remain provider-neutral.

Future provider fields may include:

- provider
- provider reference
- provider status
- failure reason

Gateway webhooks such as refund success/failure/reversal must enter through the canonical service and validated state transition rather than directly mutating model fields.

This supports providers with asynchronous refund processing and provider-specific lifecycle events.

## 15. Auditability

Every refund event must preserve enough information to answer:

- who requested it,
- when it was requested,
- how much was returned,
- why it was returned,
- which payment it belongs to,
- which idempotency operation created it,
- what provider reference exists when integrated,
- what final state was reached,
- why a refund failed when it failed.

A broader immutable financial audit-log subsystem remains a future architecture phase, but refund records themselves must be auditable from day one.

## 16. Security / Multi-Tenancy

All refund queries and mutations must be workspace scoped.

Required controls:

- workspace ownership validation,
- tenant/payment relationship validation where applicable,
- service-level authorization,
- API-level authorization,
- PostgreSQL RLS consistent with existing financial tables,
- cross-workspace access tests,
- no leakage through idempotency lookup,
- no cross-workspace payment references accepted by the service.

## 17. Error Contract

The service should expose deterministic domain errors for:

- payment not found,
- unauthorized mutation,
- invalid amount,
- refund capacity exceeded,
- invalid refund state transition,
- idempotency conflict,
- workspace mismatch,
- unsupported refund target (for example deferred AdvanceCredit refund).

Errors must not expose another workspace's payment existence.

## 18. Testing Strategy

Before implementation is considered complete, tests must cover at minimum:

### Model / database

- valid refund creation,
- positive amount constraint,
- valid state choices,
- workspace ownership,
- immutability expectations,
- idempotency uniqueness,
- RLS isolation.

### Service

- full refund,
- partial refund,
- multiple partial refunds,
- capacity exhaustion,
- concurrent refund attempts,
- idempotent retry,
- idempotency conflict,
- failed refund reservation release,
- successful refund persistence,
- cross-workspace payment rejection,
- manager/admin/owner authorization.

### API

- successful creation,
- invalid payload,
- unauthorized role,
- cross-workspace payment hidden,
- idempotent retry,
- capacity error contract.

### Integration

- payment remains immutable,
- allocation remains immutable,
- advance credit remains unchanged,
- Phase 3.9-B financial position remains unchanged by refund creation,
- webhook/state-transition path uses the canonical service.

## 19. Ledger / Reconciliation Handoff

3.9-C intentionally does not implement a general ledger.

The future ledger/reconciliation phase will consume:

- payment events,
- allocation events,
- advance-credit events,
- financial adjustments,
- refund events,
- refund reversal events,

and derive accounting balances from immutable financial history.

This prevents 3.9-C from prematurely creating accounting rules that belong to the ledger layer.

## 20. Explicit Non-Goals

The following remain deferred:

- customer wallet/refundable balance,
- AdvanceCredit refunds/redemption,
- generic payment cancellation/reversal,
- chargebacks,
- disputes,
- gateway-specific business logic,
- accounting/GL ledger,
- reconciliation engine,
- tax/GST refund accounting,
- credit-note document lifecycle,
- refund approval thresholds / maker-checker,
- bulk refunds,
- UI/admin workflow,
- automated invoice-status redesign.

## 21. Open Architecture Decisions Before Coding

The following must be explicitly finalized before Phase 3.9-C implementation:

1. **Refundable capacity policy:** whether allocated/captured payment amounts are refundable in core, and the exact formula.
2. **Reservation semantics:** which statuses reserve capacity and when failed/expired attempts release it.
3. **Refund state ownership:** which transitions are synchronous versus gateway-confirmed.
4. **Provider abstraction:** minimal provider-neutral fields required for the first implementation.
5. **Refund reversal scope:** model now versus reserved future extension.
6. **Payment-level versus allocation-level attribution:** confirm payment-first core model.
7. **Authorization:** confirm owner/admin/manager baseline without approval workflow.
8. **Invoice impact:** confirm no automatic `Invoice.status` reinterpretation.
9. **Idempotency contract:** exact operation fingerprint and conflict semantics.
10. **Audit contract:** required immutable fields for the initial model.

## 22. Architecture Decision Summary

**Recommended direction:** implement 3.9-C as a **Payment Refund / Cash Reversal event subsystem**, not as another invoice adjustment feature.

The subsystem must preserve the existing financial architecture and immutable historical records while adding a new cash-side event stream. Refunds are payment-centric, concurrency-safe, idempotent, workspace-isolated, provider-neutral, and routed through a canonical service.

No Phase 3.9-C production model/service/API implementation should begin until the open decisions in Section 21 are reviewed and locked.
