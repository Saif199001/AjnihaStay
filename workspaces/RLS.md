# Workspace Row-Level Security

AjnihaStay uses PostgreSQL Row-Level Security as a second tenant-isolation boundary behind application workspace authorization.

## Architecture

The API resolves an active workspace membership first. Workspace permissions bind `app.workspace_id` for the current PostgreSQL transaction. PostgreSQL policies use that setting to enforce workspace isolation at the database layer.

The authoritative RLS inventory and policy registry is maintained in:

```text
workspaces/management/commands/enable_workspace_rls.py
```

The deployment command is the policy synchronization point. It enables and `FORCE`s RLS and recreates the authoritative `workspace_isolation_<table>` policy for every currently workspace-owned table.

The current inventory covers 26 domain tables, including:

- properties_property
- properties_propertyimage
- unit_unit
- unit_unitimage
- unit_subunit
- tenant_tenant
- tenant_occupancy
- tenant_charge
- payments_invoice
- payments_payment
- payments_paymentallocation
- payments_billingschedule
- payments_advancecredit
- payments_advancecreditapplication
- payments_financialadjustment
- payments_paymentrefund
- payments_financialledgerentry
- leasing_lease
- applications_applicant
- applications_application
- applications_applicationevent
- kyc_kycprofile
- kyc_kycdocument
- kyc_kycverificationevent
- kyc_kycdocumentevent
- kyc_agreementlink

Tables with a direct `workspace_id` use that FK as the primary policy boundary. Tables without a direct workspace FK derive workspace ownership through their protected parent relationship.

## Pure advance payments

`payments_payment` has a direct `workspace_id` FK and may have `invoice_id = NULL` for a pure advance receipt. Its RLS policy therefore uses `Payment.workspace_id` rather than requiring an invoice relationship.

This is required for the canonical flow:

```text
invoice-less Payment
    -> AdvanceCredit
    -> future Invoice application
```

## Fail-closed workspace context

The policy registry uses:

```sql
NULLIF(current_setting('app.workspace_id', true), '')::bigint
```

A missing or empty workspace context therefore evaluates to `NULL`, causing protected-table policies to match no rows.

Application code must still establish workspace context before querying protected domain data. RLS is a database safety net, not a replacement for application authorization.

## Activation / deployment

RLS policy synchronization must happen after all migrations have created the current domain tables:

1. Set `DB_RLS_ENABLED=true` in the application environment.
2. Run migrations.
3. Run:

```bash
python manage.py enable_workspace_rls
```

4. Verify the command succeeds before accepting application traffic.
5. Restart/reload the application if required by the deployment platform.

The command fails closed if an expected workspace-owned table is missing from the database. This prevents a partial deployment from silently activating an incomplete RLS inventory.

The runtime application database role must not have `BYPASSRLS`.

## Transaction context

`set_config('app.workspace_id', <workspace>, true)` is transaction-local. `ATOMIC_REQUESTS` is enabled when `DB_RLS_ENABLED=true`, so normal API requests keep the selected workspace context for the request transaction.

Non-request/background entry points must establish their own explicit transaction-local workspace context before accessing protected domain data.

## Restricted-role validation

The RLS regression suite creates a PostgreSQL role with:

```text
NOSUPERUSER
NOBYPASSRLS
```

and grants only the required table access. Tests then execute protected queries under that role with `SET ROLE` and verify the database policy itself, not only Django application filters.

The suite verifies, at minimum:

- the role is not a superuser;
- the role cannot bypass RLS;
- every authoritative table has RLS enabled;
- every authoritative table has RLS forced;
- every authoritative table has its expected workspace policy;
- missing workspace context returns no protected rows;
- a selected workspace exposes only its own rows;
- pure invoice-less advance payments remain visible inside their workspace;
- cross-workspace inserts are rejected;
- cross-workspace updates cannot modify another workspace;
- payment allocations remain workspace-isolated.

## Django Admin

Django Admin is a platform-level administrative surface, not a workspace-scoped customer API. With `FORCE ROW LEVEL SECURITY`, a database role without RLS bypass privileges cannot safely perform unrestricted cross-workspace customer-domain operations.

The normal application database role must remain a non-bypass role. Granting `BYPASSRLS` is not an acceptable workaround for customer-domain access.

## Emergency rollback

RLS rollback is an operational emergency procedure only. If temporarily disabling RLS is required, diagnose the workspace context and deployment configuration before re-enabling the authoritative policy set.

## Important

Do not run production domain queries without a workspace context after RLS is enabled. A missing `app.workspace_id` must fail closed and return no matching protected rows.
