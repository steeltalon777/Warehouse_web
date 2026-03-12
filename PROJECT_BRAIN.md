# PROJECT_BRAIN

## Project mission
Evolve Warehouse_web into a Django control panel over SyncServer domain APIs.

## Current architecture intent
- Django: technical auth/admin/staff + UI.
- SyncServer: domain truth and business entities.

## Legacy status
- `UserProfile`, `Site`, `Role` in `apps/users` are deprecated compatibility artifacts.
- They should not be mandatory for auth flow.

## Roadmap direction
1. Move all warehouse user/role/site flows to SyncServer-backed APIs.
2. Keep catalog/balances/operations as API-first through SyncServer.
3. Support multiple clients (web/WPF/mobile/offline) with same SyncServer domain users.
4. Gradually phase out legacy Django profile dependency.
