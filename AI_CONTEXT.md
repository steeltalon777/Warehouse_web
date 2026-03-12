# AI_CONTEXT

## Purpose
Warehouse_web = Django SSR client for warehouse operations backed by SyncServer.

## Do/Don't
- DO: вызывать SyncServer API через service/client слои.
- DO: поддерживать PostgreSQL service DB для Django в production.
- DON'T: делать Django ORM источником истины для users/sites/catalog/balances/operations.
- DON'T: завязывать auth flow на обязательный `UserProfile`.

## Main entry points
- `apps/client/views.py` — role-oriented UX (root/chief/storekeeper).
- `apps/catalog/views.py` — chief catalog management via API-first services.
- `apps/integration/syncserver_client.py` — integration contract.
