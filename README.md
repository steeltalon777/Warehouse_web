# Warehouse_web

## Project overview
Warehouse_web is a Django SSR web/admin client for warehouse operations UI.

**Architecture role split:**
- **SyncServer (FastAPI)** is the source of truth for domain data: users, roles, sites, catalog, balances, operations, devices, events.
- **Warehouse_web (Django)** is a technical web layer (admin/staff/root access, sessions, templates, orchestration).

## Source-of-truth policy
Django must not be a source of truth for warehouse domain entities.

Django DB stores only:
- technical admin/staff/superuser auth/session/admin tables
- service/UI technical data

Domain users/roles/sites/catalog must be served via SyncServer API.

## Runtime architecture
`Browser -> Django Views -> Service layer -> SyncServer client -> SyncServer API -> PostgreSQL(domain)`

## Database split
- **Django service DB**: separate PostgreSQL database for Django auth/admin/session/service data.
- **SyncServer domain DB**: separate domain database/schema for warehouse truth.
- **Production**: sqlite is not allowed.

## Legacy notice
`apps/users` contains legacy transition models (`UserProfile`, `Site`, `Role`).
They are deprecated and must not be mandatory in Django auth flow.

## Key env
- `DJANGO_ENV=production`
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE`
- `SYNC_SERVER_URL` (in Docker network: `http://syncserver:8000`)
- `SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`, `SYNC_CLIENT_VERSION`, `SYNC_SERVER_TIMEOUT`

## Run
```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```
