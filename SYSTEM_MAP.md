# SYSTEM_MAP

## Components
- Browser
- nginx gateway (production ingress)
- Warehouse_web (Django web/admin client)
- SyncServer (FastAPI source of truth)
- PostgreSQL (separate DBs/schemas for Django service data and SyncServer domain data)

## Ownership boundaries
- **SyncServer owns domain truth**: users, roles, sites, catalog, balances, operations, devices, events.
- **Warehouse_web owns technical web layer**: Django auth/session/admin/staff/superuser + UI orchestration.

## Data flow
`Browser -> Warehouse_web -> SyncServerClient -> SyncServer API -> Domain DB`

## Legacy transition layer
`apps/users/models.py` (`UserProfile`, `Site`, `Role`) is legacy/deprecated and optional.
It must not be required for Django superuser/staff login or permission checks.
