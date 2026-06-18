# SYSTEM_MAP

## Context

`Browser -> Django UI/BFF -> Service Layer -> apps/sync_client -> SyncServer API`

## Django Responsibilities

1. Technical auth, session, and admin layer.
2. Role-oriented web UI.
3. Same-origin BFF endpoints for Angular.
4. SyncServer integration orchestration.

## Main Modules

- `apps/sync_client/*` - HTTP clients and endpoint wrappers for SyncServer.
- `apps/catalog/services.py` - SyncServer-backed catalog orchestration.
- `apps/catalog/views.py` - catalog/nomenclature views and BFF candidates.
- `apps/client/services.py` - dashboard/domain orchestration.
- `apps/users/*` - Django auth and SyncServer user binding.

## UI Routes

- Root/admin: `/client/root/users/`, `/client/root/users/create/`, `/client/root/users/<id>/edit/`.
- Catalog/nomenclature: `/catalog/*`, `/nomenclature/*`.
- Storekeeper: `/client/catalog/`, `/client/balances/`, `/client/operations/`, `/client/operations/create/`.
