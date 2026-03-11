# ARCHITECTURE

## System Overview
Warehouse_web is a Django SSR **client application** for warehouse operators.
It provides authentication, authorization, and web UI workflows.

SyncServer is an external backend (FastAPI + PostgreSQL) and remains the **source of truth** for catalog master data.

## Core invariant
- SyncServer = source of truth.
- Warehouse_web = client layer.
- Warehouse_web must not directly read/write SyncServer PostgreSQL.
- Integration path is HTTP only.

## High-Level Architecture
```text
Browser
  -> Django URLs/Views (Warehouse_web)
  -> CatalogService
  -> SyncServerClient (httpx)
  -> SyncServer API
  -> PostgreSQL (owned by SyncServer)
```

Warehouse_web local DB is used only for app-side concerns (auth/session/admin/local metadata).

## Layers and key files
- URL/API layer:
  - `config/urls.py`
  - `apps/catalog/urls.py`, `apps/users/urls.py`, `apps/client/urls.py`
- UI/application layer:
  - `apps/catalog/views.py`
  - `apps/client/views.py`
- Service layer:
  - `apps/catalog/services.py`
- Integration layer:
  - `apps/integration/syncserver_client.py`
- Settings/runtime:
  - `config/settings/base.py`
  - `config/settings/development.py`
  - `config/settings/production.py`

## Data and integration flow
```text
Request -> Django View -> CatalogService -> SyncServerClient -> SyncServer API
       <- Template rendering <- ServiceResult <- HTTP response mapping
```

## Operational architecture
- Settings selected by `DJANGO_ENV` (`development` / `production`).
- Environment-driven security and connection configuration via `.env`.
- Static pipeline uses `STATIC_ROOT` + WhiteNoise in production mode.
- Health endpoints:
  - `/healthz/` (app liveness)
  - `/healthz/sync/` (dependency health)
