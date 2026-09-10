# B1 — Dashboard Canonical Financial Truth

**Status:** IMPLEMENTATION READY FOR CI  
**Date:** 2026-09-10

## Objective

Align dashboard financial reads with the locked Phase 3 canonical financial equation rather than legacy invoice compatibility fields or allocation-only arithmetic.

## Canonical Read Equation

For every workspace invoice:

```text
Adjusted Receivable = Gross Receivable + Debit Adjustments - Reducing Adjustments
Outstanding = max(Adjusted Receivable - Payment Allocations - Advance Credit Applications, 0)
```

Reducing adjustments are credit, discount, waiver and write-off.

Dashboard outstanding and overdue are derived from these immutable financial components. `Invoice.paid_amount` and `Invoice.status` remain compatibility fields and are not authoritative for dashboard financial truth.

## Refund Boundary

`PaymentRefund` represents cash returned from a payment. It does not reduce invoice receivable or invoice outstanding. B1 does not reinterpret refund `updated_at` as a financial event timestamp. Net cash reporting remains a separately scoped read-model concern until a dedicated refund settlement/event timestamp contract exists.

## Compatibility / Safety

- Existing dashboard response keys remain stable.
- No financial mutation path is changed.
- Workspace filtering remains mandatory.
- Dashboard remains read-only.

## Required Test Gate

- Reducing adjustment lowers dashboard outstanding.
- Debit adjustment increases dashboard outstanding.
- Advance-credit application reduces dashboard outstanding.
- Stale legacy `paid_amount` does not change dashboard outstanding/overdue.
- Overdue uses canonical outstanding.
- Cross-workspace financial data is excluded.
- Existing operational dashboard contract remains green.
