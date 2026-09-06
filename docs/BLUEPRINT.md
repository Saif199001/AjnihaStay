# AjnihaStay — Market/Product Blueprint v2.0

**Status:** LOCKED  
**Strategy:** India-first, globally extensible  
**Purpose:** Product source of truth

## 1. Product Vision

AjnihaStay is a flexible **Property Operating & Financial Management SaaS** for residential rental, PG/hostel, co-living, commercial and mixed-use property businesses.

> One property operating system that adapts to different property business models without requiring a separate product for each property type.

Core lifecycle:

`Property → Occupancy → Charges → Invoices → Payments → Operations → Reporting → Automation`

## 2. Product Positioning

AjnihaStay is not only a PG app, landlord rent tracker, accounting app, payment collection tool, or property marketplace.

It is positioned as:

> **A configurable property operating system with a built-in financial engine and automation layer.**

## 3. Strategic Product Layers

1. **Property Operating Engine** — Workspace, Property, Unit, SubUnit, Tenant, Occupancy, Operations.
2. **Financial Engine** — Charge, Invoice, Payment, recurring billing, Ledger, Settlement, Reconciliation, Accounting.
3. **Automation + AI Layer** — WhatsApp, notifications, rules, collections, billing automation, insights and AI assistance.

The domain/financial engine remains the source of truth; automation and AI operate on top of it.

## 4. Existing Capability Preservation — NON-NEGOTIABLE

Blueprint v2 extends the existing product. It does not reset or unnecessarily redesign validated implementation.

Protected existing capabilities include:

- Workspace and multi-tenancy
- Membership/RBAC and RLS architecture
- Property, Unit and SubUnit management
- Unit capacity and occupancy semantics
- Tenant and occupancy management
- Operational dashboard
- Charge, Invoice and Payment lifecycle
- **Partial payments**
- **Advance payments / advance billing**
- **Arrear / arrears billing**
- Existing financial validations and transactional protections
- Existing API/domain contracts
- Existing workspace isolation and integrity rules

### Golden Rule

> **No regression of existing supported business workflows.**

New capabilities must extend the existing model and preserve partial payments, advance handling, arrears, occupancy semantics, capacity semantics, multi-tenancy and workspace isolation. Any breaking change requires explicit architectural approval.

## 5. Property Model

Canonical foundation:

```text
Workspace
  └── Property
       └── Unit
            └── SubUnit
                 └── Occupancy
                      └── Tenant
```

The hierarchy is intentionally generic and can represent:

- Residential houses and apartments
- PGs
- Hostels
- Co-living
- Commercial shops/offices
- Mixed-use properties

Property type should primarily configure workflows, billing rules, occupancy rules, reporting and presentation before introducing separate core models.

## 6. Tenant & Occupancy Engine

Tenant represents the person/entity. Occupancy represents the tenant's relationship with a space over a period.

The system must preserve date-aware and capacity-aware occupancy semantics and support future transfers, historical occupancy, vacancies, renewals and move-in/move-out workflows.

## 7. Financial Engine

Existing foundation:

```text
Occupancy
   ↓
Charge
   ↓
Invoice
   ↓
Payment
```

The financial engine will expand to support recurring billing, allocation, credits/debits, adjustments, deposits, refunds, late fees, write-offs, settlement, reconciliation and accounting.

### Financial Truth Principle

> **Financial state must have one canonical transition authority.**

Existing behavior is preserved, but future hardening must eliminate competing state mutation across model saves, signals and services. The long-term direction is:

`Business Event → Canonical Financial Service → Financial State → Ledger/Reporting/Automation`

## 8. Billing Models

Supported/protected:

- Recurring rent/charges
- Partial payments
- Advance billing/payments
- Arrear billing

Future extensions:

- Proration
- Discounts
- Credits and adjustments
- Late fees and grace periods
- Deposits/refunds
- Automated invoice generation
- Configurable billing schedules
- Utility/service billing

## 9. India-First Layer

AjnihaStay will be optimized for Indian workflows, including:

- UPI
- Indian payment gateways
- WhatsApp
- SMS and email
- Tenant KYC
- Rental agreements
- eSign
- Indian address formats
- UTR/payment references
- GST/tax readiness
- INR and Indian operational conventions

Sensitive KYC documents must use private/authenticated storage and controlled delivery. Public property media and private identity documents must not share an inappropriate security model.

## 10. Leasing Engine

Future leasing capabilities:

- Availability and leads
- Applications
- Applicant information/screening
- Lease creation/templates
- eSign
- Move-in/move-out
- Renewals
- Notice periods
- Lease expiry
- Deposits

## 11. Commercial Property Capability

Long-term commercial support includes:

- Commercial leases
- Escalation rules
- Security deposits
- CAM/NNN-style charges where applicable
- Utility/service charges
- Tenant-specific billing rules
- Renewals and notice periods

Commercial functionality should extend the generic property and financial engines.

## 12. Operations

Future operations module:

- Maintenance requests
- Complaints
- Work orders
- Assignment and staff workflows
- Vendors
- Vendor payments
- Status/priority
- Attachments and history

Expense/vendor management will include property expenses, vendor bills/payments, recurring expenses, categories, attachments and approvals.

## 13. Portals

### Tenant Portal

Profile, KYC, agreements, occupancy, charges, invoices, payments, receipts, outstanding dues, maintenance requests, notices and documents.

### Owner Portal

Portfolio, occupancy, revenue, expenses, collections, outstanding, statements, documents, distributions and maintenance visibility.

## 14. Communication & Automation

Communication channels:

`WhatsApp · SMS · Email · In-app notifications`

Automation use cases include rent/invoice/payment reminders, arrears, late fees, lease expiry, renewal, maintenance updates and vacancy alerts.

Automation must reduce operational work rather than create additional manual administration.

## 15. AI Strategy

AI operates on trusted domain data and never becomes the source of financial truth.

Potential capabilities:

- Natural-language property queries
- Financial summaries
- Collection and arrears insights
- Vacancy insights
- Maintenance triage
- Communication drafting
- Automated report summaries
- Anomaly detection
- Natural-language dashboard

## 16. Dashboard Strategy

The existing dashboard remains the **Operational Control Center** and is protected.

It covers property/unit capacity, occupancy, available spaces, active tenants, subunits, upcoming vacancies, invoiced/rent/charges, collections, collection percentage, outstanding and overdue amounts.

Historical analytics and advanced BI are future layers.

## 17. Security & Multi-Tenancy

Workspace remains the SaaS tenant boundary. Security requirements include workspace isolation, RBAC, RLS defense-in-depth, secure authentication, private KYC access, audit logging, financial integrity, transactional consistency, rate limiting, secure secrets, backups and production security checks.

Membership role remains the canonical workspace authorization model. Legacy role concepts must eventually be retired or clearly separated.

## 18. Product Roles

Workspace roles will evolve from the existing Owner/Admin/Manager/Staff model toward optional Accountant and other specialized roles. External roles include Tenant/Resident, Owner/Investor and Vendor. Platform-level administration must remain separate from customer workspace authorization.

## 19. Reporting

Reporting roadmap:

- Operational: occupancy, vacancy, collections, outstanding, arrears, upcoming vacancies
- Financial: revenue, expenses, P&L, cash flow, receivables, payables, rent roll
- Portfolio: property/unit performance and trends
- Advanced: forecasting, collection prediction, vacancy prediction and anomaly detection

## 20. Differentiation

AjnihaStay's differentiation is the combination of:

1. Flexible property model
2. Deep financial lifecycle
3. Existing support for partial, advance and arrear workflows
4. India-native payments/communication/KYC capabilities
5. Automation-first operations
6. Enterprise-ready multi-tenancy, RBAC and RLS foundation

Positioning should emphasize a flexible property operating system rather than a single property-type application.

## 21. Competitive Strategy

Global mature property-management products establish expectations around accounting, payments, leasing, maintenance, portals, reporting and automation. India-focused products establish expectations around WhatsApp, KYC, room/bed inventory, recurring rent and local collection workflows.

AjnihaStay should not copy one competitor. The strategic combination is:

`Global-grade architecture + India-native workflows + Flexible property model + Deep financial engine + Automation`

## 22. Product Scope

### Core

Workspace, RBAC, Property, Unit, SubUnit, Tenant, Occupancy, Charges, Invoices, Payments, partial payments, advance, arrears and dashboard.

### Expansion

Recurring billing, Ledger, Settlement, Accounting, UPI/payment gateways, KYC, agreements, WhatsApp, maintenance, expenses, vendors, leasing, owner portal and tenant portal.

### Intelligence

Rules, notifications, collection automation, AI, forecasting and anomaly detection.

## 23. Roadmap

```text
Phase 0  Security / Baseline                  ✅
Phase 1  Workspace / RBAC / RLS               ✅
Phase 2  Domain Hardening                     ✅
Phase 2.7 API / Read Models / Dashboard      HARDENING

Phase 3  Financial Lifecycle
         Canonical financial transitions
         Recurring billing
         Settlement
         Ledger foundations
         Financial integrity

Phase 4  India Financial Layer
         UPI / payment gateway
         Automated collection
         WhatsApp
         Receipts / reconciliation

Phase 5  Leasing + KYC
         Applications / agreements / eSign
         KYC workflow / move-in-out / renewals

Phase 6  Operations
         Maintenance / expenses / vendors / work orders

Phase 7  Portals
         Tenant Portal / Owner Portal

Phase 8  Automation
         Rules / notifications / billing & collection automation

Phase 9  AI
         AI Assistant / insights / predictions
```

Exact implementation sequencing may be refined after each architecture audit, but product direction remains governed by this blueprint.

## 24. Phase 3 Priority

Phase 3 begins with the financial foundation rather than attempting a complete accounting suite at once:

1. Financial state architecture
2. Canonical financial transition service
3. Recurring billing foundation
4. Charge generation
5. Invoice generation
6. Payment allocation
7. Preserve partial payments
8. Preserve advance payments
9. Preserve arrears
10. Settlement foundation
11. Ledger foundation
12. Financial reporting

## 25. Non-Goals

AjnihaStay will not initially become a generic ERP, generic accounting package, real-estate marketplace, CRM-only product, banking product, payment gateway itself, construction-management platform, generic HR/payroll system or social network. Integrations may connect adjacent ecosystems where strategically useful.

## 26. Product Principles

1. Existing validated functionality is protected.
2. Domain truth lives in the backend domain/service layer.
3. Financial state has one canonical transition authority.
4. Workspace isolation is non-negotiable.
5. Property type configures workflows before it creates new core models.
6. AI never becomes financial truth.
7. Automation must reduce work.
8. Every feature must solve a real user/market problem.
9. Competitor features are not sufficient justification by themselves.
10. Backend/domain contracts are stabilized before UI-driven architecture decisions.

## 27. Blueprint Lock

This document is the product-direction baseline for AjnihaStay.

Every new feature must answer:

1. What user/market problem does it solve?
2. Which property/business model needs it?
3. Does it extend existing architecture?
4. Does it preserve existing functionality?
5. What domain model owns the truth?
6. What financial implications exist?
7. What security/tenant-isolation implications exist?
8. What automation opportunity exists?
9. What is its priority?
10. Does it belong in the current phase?

If these questions cannot be answered, the feature should not enter implementation yet.

**Status: LOCKED 🔒**
