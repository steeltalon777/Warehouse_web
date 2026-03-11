# ARCHITECTURE

## System Overview
Warehouse_web is a Django SSR client for warehouse users. It handles authentication, authorization, and web UI, while catalog master data is managed by external SyncServer.

## High-Level Architecture
```text
Clients (Browser)
  ↓
API / Application Layer (Django URLs + Views)
  ↓
Service Layer (CatalogService)
  ↓
Repository / Data Layer (SyncServerClient + local ORM)
  ↓
Databases
  - Local Django DB (auth/session/local metadata)
  - SyncServer PostgreSQL (catalog source of truth)
```

## Application Layers
### API layer
- `config/urls.py`
- `apps/catalog/urls.py`, `apps/users/urls.py`, `apps/client/urls.py`
- `apps/catalog/views.py`, `apps/client/views.py`, `apps/users/views.py`

### Service layer
- `apps/catalog/services.py` (`CatalogService`, `ServiceResult`)

### Repository / data layer
- External: `apps/integration/syncserver_client.py` (`SyncServerClient` over HTTP)
- Local: Django ORM models in `apps/*/models.py`

### Models / entities
- Catalog entities: `Category`, `Unit`, `Item`
- Access entities: `Site`, `UserProfile`, `Role`

## Data Model
- Local persistent data: Django auth/admin/session + local domain models.
- Catalog runtime source of truth: SyncServer (not local Django DB).

## Data Flow
```text
Client request
  → Django View
  → CatalogService
  → SyncServerClient
  → SyncServer API
  → Response mapped to ServiceResult
  → Template rendering
```

## Architectural Principles
- SyncServer is canonical source for catalog domain.
- No direct catalog master-data writes from Django app to SyncServer PostgreSQL.
- Views use service layer, not low-level HTTP client directly.
- Integration errors are mapped to predictable user-facing results.

## External Integrations
- SyncServer HTTP API.
- Device/site identity headers:
  - `X-Site-Id`
  - `X-Device-Id`
  - `X-Device-Token`
  - `X-Client-Version`

## Future Architecture
- Add production settings split (`base/dev/prod`).
- Add production runtime stack (Gunicorn + static strategy + containerization).
- Extend `apps/documents` using the same layered approach.
