# AjnihaStay — Blueprint v2 vs Current Backend Gap Audit

**Status:** LOCKED  
**Version:** v1.0  
**Date:** 2026-09-06  
**Branch:** `phase-1/workspace-multitenancy`

## Purpose

This document freezes the implementation gap between the locked Market/Product Blueprint v2 and the current AjnihaStay backend. It is the implementation planning source of truth for extending the backend without destabilizing capabilities that are already built.

## Non-Negotiable Preservation Rules

The following existing capabilities are protected and must not be removed or semantically regressed during future work:

- Workspace / membership / RBAC architecture
- PostgreSQL RLS and tenant-isolation architecture
- Property → Unit → SubUnit hierarchy
- Unit capacity and date-aware occupancy semantics
- Tenant and Occupancy domain model
- Advance billing
- Arrears billing
- Monthly and daily billing cycles
- Partial payments
- Existing Charge → Invoice → Payment financial flow
- Security deposit support
- Existing settlement calculation foundation
- Dashboard read model and API contract
- Existing API/domain contracts unless a versioned change is explicitly approved
- UI repositories and UI implementation during backend hardening

**Important terminology rule:** advance billing and advance payment credit are different concepts. Existing advance billing must remain intact; any future prepaid/advance-credit system must be additive and must not break current invoice/payment semantics.

## Status Legend

- 🟢 Implemented / compatible
- 🟡 Foundation exists; expansion required
- 🔴 Missing
- 🔵 Future / intentionally deferred
- 🔒 Protected existing capability

## Gap Matrix

### 1. Multi-tenancy & Security

| Capability | Status | Direction |
|---|---|---|
| Workspace | 🟢 | Preserve |
| Membership / RBAC | 🟢 | Preserve |
| PostgreSQL RLS | 🟢 | Preserve + deployment hardening |
| Protected domain admin architecture | 🟢 | Preserve |
| Audit logging | 🔴 | Future domain/security layer |
| Private KYC document delivery | 🟡 | Harden |
| Browser auth abuse/rate limiting | 🟡 | Harden |
| Production security gate | 🟡 | Expand CI/deployment |

### 2. Property Operating Engine

| Capability | Status | Direction |
|---|---|---|
| Property | 🟢 | Preserve |
| Unit | 🟢 | Preserve |
| SubUnit | 🟢 | Preserve |
| Unit capacity | 🟢 | Preserve |
| Tenant | 🟢 | Preserve |
| Occupancy | 🟢 | Preserve |
| Date-aware occupancy | 🟢 | Preserve |
| Capacity validation | 🟢 | Preserve + concurrency hardening |
| Property images | 🟢 | Preserve; add primary-image integrity later |
| Generic property-type support | 🟢 | Extend through configuration/domain features, not rewrite |

### 3. Tenant / KYC

| Capability | Status | Direction |
|---|---|---|
| Tenant profile | 🟢 | Preserve |
| KYC fields | 🟢 | Preserve |
| KYC document storage | 🟡 | Secure/private delivery |
| KYC verification workflow | 🔴 | Add |
| Verification history/status | 🔴 | Add |
| Document expiry tracking | 🔴 | Add |
| Agreement linkage | 🔴 | Add |

### 4. Occupancy / Leasing Foundation

| Capability | Status | Direction |
|---|---|---|
| Advance billing | 🔒 🟢 | Preserve |
| Arrears billing | 🔒 🟢 | Preserve |
| Monthly billing | 🟢 | Preserve |
| Daily billing | 🟢 | Preserve |
| Rent | 🟢 | Preserve |
| Check-in / check-out | 🟢 | Preserve |
| Security deposit | 🟢 | Preserve |
| Transfer workflow | 🔴 | Future |
| Renewal workflow | 🔴 | Future |
| Notice period | 🔴 | Future |
| Lease entity / agreement | 🔴 | Future |

### 5. Financial Engine

Current core:

`Occupancy → Charge → Invoice → Payment`

| Capability | Status | Direction |
|---|---|---|
| Charge | 🟢 | Preserve |
| Invoice | 🟢 | Preserve |
| Payment | 🟢 | Preserve |
| Partial payment | 🔒 🟢 | Preserve exactly |
| Advance billing | 🔒 🟢 | Preserve exactly |
| Arrear billing | 🔒 🟢 | Preserve exactly |
| Outstanding calculation | 🟢 | Preserve |
| Overdue calculation | 🟢 | Preserve |
| Security deposit | 🟢 | Preserve |
| Final settlement calculation | 🟡 | Evolve into lifecycle |
| Recurring billing engine | 🔴 | Phase 3 |
| Automated charge generation | 🔴 | Phase 3 |
| Payment allocation engine | 🔴 | Phase 3 |
| Advance payment / prepaid credit | 🔴 | Phase 3; additive |
| Refunds | 🔴 | Phase 3 |
| Adjustments | 🔴 | Phase 3 |
| Credits / debits | 🔴 | Phase 3 |
| Discounts | 🔴 | Phase 3 |
| Late-fee engine | 🔴 | Phase 3 |
| Write-offs | 🔴 | Later financial layer |
| Ledger | 🔴 | Phase 3 foundation |
| Reconciliation | 🔴 | Phase 4+ |
| Accounting / GL | 🔴 | Later |

### 6. Important Existing Financial Semantics

Existing Invoice supports pending/partial/paid states and derives paid amount from payments. Payment creation validates against the remaining invoice amount and uses an invoice row lock in the service path. These behaviors are protected.

The current system also has settlement calculation logic, including total rent, total charges, total paid, total due, security deposit and final balance. This is a foundation to evolve, not a reason to replace the current financial model.

A future advance-credit capability must distinguish:

- **Advance billing:** when an invoice is generated/collected before the service period.
- **Advance payment credit:** money received beyond the currently allocated invoice amount and carried forward for future allocation.

The latter is currently missing and must be introduced without weakening the existing rule that normal invoice payments cannot exceed their remaining balance.

### 7. Charge Engine

Current charge types and charge validation are implemented. A full engine is missing.

Future additions:

- Charge rules
- Recurring charges
- Scheduled charges
- Metered charges
- Automated charge generation
- Proration
- Tax support where applicable
- Discount support
- Late fees

### 8. Invoice Engine

Current invoice primitive is implemented with billing dates, rent, charges, total, paid amount, due date, invoice number and status.

Missing lifecycle capabilities:

- Recurring invoice generation
- Line-item model where required
- Credits / debits
- Discounts
- Taxes
- Late fees
- Adjustments
- Void / cancellation lifecycle
- Credit notes / debit notes where product requirements justify them

### 9. Payment Engine

Current payment methods include cash, UPI, bank transfer and card. Payment creation is transactionally protected in the service layer.

Missing:

- Payment gateway integration
- Payment links
- Gateway transaction state
- Webhooks
- Failed-payment lifecycle
- Retry
- Payment allocation across invoices
- Advance-credit handling
- Refunds
- Settlement / reconciliation workflow
- UTR / bank reconciliation workflow

### 10. Commercial Property

The generic property/unit hierarchy is architecture-ready for shops, offices and mixed-use properties.

Missing commercial domain capabilities:

- Lease terms
- Escalation schedules
- CAM
- NNN / recoveries where applicable
- Commercial recurring billing rules
- Tenant-specific billing rules
- Commercial renewal lifecycle

No core Property → Unit → SubUnit rewrite is approved or required.

### 11. Maintenance / Operations

A maintenance charge type exists, but that is financial charging, not maintenance operations.

Missing:

- Maintenance request
- Work order
- Assignment
- Priority
- Status lifecycle
- Vendor linkage
- Attachments
- Maintenance history

### 12. Expenses / Vendors

Missing:

- Expense
- Vendor
- Vendor bill
- Vendor payment
- Approval workflow
- Recurring expenses

### 13. Communications / India Layer

Missing or incomplete product layers:

- WhatsApp provider integration
- WhatsApp templates
- Delivery status / retry
- Opt-in / opt-out
- Automated payment reminders
- Payment links
- UPI gateway integration
- Notification event/rule system

The existing `upi` payment method is only a payment-method value; it is not itself a gateway integration.

### 14. KYC / Agreements

KYC data fields exist, but workflow and secure delivery are incomplete.

Future:

- Verification states
- Verification audit history
- Document expiry
- Private/authenticated document delivery
- Rental/lease agreement
- eSign integration

### 15. Portals

Dedicated tenant and owner portals are not implemented.

Future:

- Tenant portal
- Owner portal
- Portal-specific read models and permissions
- Payment / document / maintenance workflows

### 16. Automation

A general automation/rules engine is not implemented.

Target model:

`Trigger → Condition → Action`

Examples:

- Invoice overdue → late fee + reminder
- Upcoming vacancy → manager notification
- Lease expiry → renewal reminder
- Payment received → receipt / notification

### 17. AI

No AI domain layer is currently implemented. AI remains a later layer after property and financial data contracts become stable and trustworthy.

## Locked Phase 3 Direction

Phase 3 is **Financial Lifecycle**, not an architecture rewrite.

Recommended sequence:

1. Financial state architecture
2. Canonical financial transition service
3. Charge engine
4. Recurring billing
5. Invoice generation lifecycle
6. Payment allocation
7. Partial-payment preservation tests
8. Advance-credit / prepaid balance
9. Arrear-billing preservation tests
10. Adjustments / credits / debits
11. Late-fee foundation
12. Settlement lifecycle
13. Ledger foundation
14. Financial reporting foundation

## Financial Architecture Rule

Invoice state must eventually have one canonical state-transition path. Current mutation is distributed across Invoice model behavior, payment signals and payment service logic. Future work must consolidate this without changing externally observable behavior of protected existing capabilities.

## Implementation Strategy

- Extend existing domain models/services where appropriate.
- Introduce new bounded financial modules instead of overloading unrelated models.
- Preserve API contracts unless a versioned contract change is explicitly approved.
- Prefer service-layer transactional workflows for financial state transitions.
- Use database constraints for invariants where they are technically safe and semantically correct.
- Do not use a naive PostgreSQL exclusion constraint for capacity-based occupancy where capacity may be greater than one.
- Keep workspace isolation/RLS intact for every new tenant-scoped model.
- Do not expose protected KYC documents through public asset delivery.
- Do not touch the UI during backend implementation unless explicitly approved.
- Every milestone follows: architecture → models → service/provider → API → tests → real integration → CI green.

## Overall Gap Assessment

| Domain | Readiness |
|---|---:|
| Multi-tenancy / security architecture | ~95% |
| Property engine | ~90% |
| Occupancy | ~85–90% |
| Tenant | ~75% |
| Basic billing | ~75% |
| Partial / advance / arrear billing semantics | Strong |
| Full financial lifecycle | ~45% |
| Accounting | ~10–15% |
| Payment integration | ~30% |
| Leasing | ~20% |
| Maintenance | ~10% |
| Portals | ~0–10% |
| Automation | ~10% |
| AI | 0% |
| Overall Blueprint v2 backend readiness | ~60–65% |

## Final Lock Decision

**KEEP the current architecture. EXTEND the missing business layers. PROTECT existing financial semantics.**

The current backend is a strong property/occupancy foundation with an incomplete higher-level financial and operational product layer. The roadmap therefore prioritizes controlled extension rather than rewrite.
