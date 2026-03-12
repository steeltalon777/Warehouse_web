# Warehouse_web

Django-приложение Warehouse_web работает как **web/admin client** поверх SyncServer API.

## Роли компонентов
- **SyncServer (FastAPI)** — source of truth для users, roles, sites, catalog, balances, operations, devices, events.
- **Warehouse_web (Django)** — SSR UI, technical admin/root/staff access, сессии и orchestration.

## Базы данных
- Django использует **отдельную service DB в PostgreSQL** (auth/session/admin/service).
- SyncServer использует отдельную domain DB/domain schema.
- В production sqlite запрещён.

## Legacy слой
`apps/users` содержит `UserProfile`, `Site`, `Role` как transition layer (deprecated).
Эти модели **не обязательны** для auth flow: superuser/staff может работать без `UserProfile`.

## UI контуры
- `/client/root/users/*` — technical root panel (управление users/roles/sites в SyncServer).
- `/catalog/*` — chief-storekeeper справочники через SyncServer API.
- `/client/catalog`, `/client/balances`, `/client/operations` — рабочий интерфейс кладовщика.

## Ключевые env
`DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE`,
`SYNC_SERVER_URL`, `SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`, `SYNC_CLIENT_VERSION`.
