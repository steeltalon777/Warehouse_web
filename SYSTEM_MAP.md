# SYSTEM_MAP

## Контекст
`Browser -> Django SSR -> Service Layer -> SyncServerClient -> SyncServer API`

## Django зоны ответственности
1. Technical auth/session/admin layer.
2. Role-oriented web UI (root/chief/storekeeper).
3. Не хранит warehouse truth в локальной ORM.

## Основные модули
- `apps/integration/syncserver_client.py` — HTTP client к SyncServer.
- `apps/catalog/services.py` — API-first сервисы каталога (chief workflows).
- `apps/client/services.py` — API-first сервисы users/roles/sites/balances/operations.
- `apps/client/views.py` — root panel + storekeeper/chief UI.
- `apps/users/*` — legacy transition models (deprecated, non-mandatory).

## UI маршруты
- Root/admin: `/client/root/users/`, `/client/root/users/create/`, `/client/root/users/<id>/edit/`
- Chief: `/catalog/*`
- Storekeeper: `/client/catalog/`, `/client/balances/`, `/client/operations/`, `/client/operations/create/`
