# Workspace Row-Level Security

Phase 1 uses PostgreSQL Row-Level Security as a second tenant-isolation boundary behind the application workspace permissions.

## Architecture

The API resolves an active workspace membership first. Workspace permissions then bind `app.workspace_id` for the current PostgreSQL transaction. PostgreSQL policies use that setting to filter workspace-owned domain rows.

The protected tables are:

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

`ATOMIC_REQUESTS` is enabled when `DB_RLS_ENABLED=true`, so the transaction-local workspace setting remains active for the complete API view. PostgreSQL `set_config(..., true)` makes the setting transaction-local.

## Activation

RLS policies are installed by migration but remain disabled until the deployment is explicitly activated.

1. Set `DB_RLS_ENABLED=true` in the application environment.
2. Run migrations.
3. Run:

```bash
python manage.py enable_workspace_rls
```

4. Restart the application.

The runtime database role must have permission to alter the tables during activation. The command uses `FORCE ROW LEVEL SECURITY`, which also subjects the table owner to the policies.

## Emergency rollback

Temporarily disable RLS with:

```bash
python manage.py disable_workspace_rls
```

Then diagnose the workspace context and deployment configuration before re-enabling it.

## Important

Do not run production domain queries without a workspace context after RLS is enabled. A missing `app.workspace_id` intentionally results in no matching protected rows.
