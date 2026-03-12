# AI_CONTEXT

## Core context
Warehouse_web is a Django SSR control panel over SyncServer APIs.

## Strict architecture rules
1. SyncServer is source of truth for: users, roles, sites, catalog, balances, operations, devices, events.
2. Django is technical web/auth layer (superuser/staff/admin/session/UI service state).
3. Domain entities must be read/changed via SyncServer API, not direct Django ORM ownership.

## Legacy handling
- `apps/users` legacy profile models are transitional and deprecated.
- They must not be mandatory for auth flow.
- Do not delete aggressively unless migration plan is explicit.

## DB context
- Production Django uses env-based PostgreSQL service DB.
- sqlite is only local/dev fallback, never production.

## Integration invariants
- Keep existing integration layer (`apps/integration/syncserver_client.py`, catalog services).
- Preserve SyncServer headers and timeout behavior.
