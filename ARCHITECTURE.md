# ARCHITECTURE

## System Overview
Warehouse_web is a Django SSR application for warehouse operators. It handles web authentication, role-based access, and catalog-facing user flows. Catalog master data is owned by SyncServer, not by Warehouse_web.

## High-Level Architecture
Clients  
↓  
API / Application Layer (Django URLs + Views)  
↓  
Service Layer (`CatalogService`)  
↓  
Repository / Data Layer (`SyncServerClient`, local Django ORM for app-local entities)  
↓  
Database (local Django DB) and external SyncServer database (through SyncServer API only)

## Application Layers
### API layer
- Root URL composition in `config/urls.py`
- App endpoints in `apps/catalog/urls.py`, `apps/users/urls.py`, `apps/client/urls.py`
- Request handling in Django views

### Service layer
- `apps/catalog/services.py`
- Encapsulates integration operations and maps SyncServer errors into predictable UI-facing results

### Repository / data layer
- `apps/integration/syncserver_client.py` for HTTP integration with SyncServer
- Django ORM models for local application state and auth-related domain data

### Models / entities
- Catalog domain models: `Category`, `Unit`, `Item`
- Access domain models: `Site`, `UserProfile`, `Role`

## Data Model
Primary entities:
- `Category`: hierarchical structure with optional parent relation
- `Unit`: measurement unit with unique code
- `Item`: inventory item linked to category and unit
- `UserProfile`: user extension with role and optional site
- `Site`: physical/organizational warehouse scope

## Data Flow
Typical catalog request flow:

Client → Django View → CatalogService → SyncServerClient → SyncServer API  
SyncServer API → SyncServerClient → CatalogService → View → Template response

## Architectural Principles
- Keep UI logic in views/templates and business orchestration in service layer
- Centralize external HTTP calls in integration client
- Keep access-control checks centralized in shared permissions module
- Treat SyncServer as source of truth for catalog master data
- Avoid direct writes to external master-data storage via Django ORM

## External Integrations
- SyncServer API over HTTP (`httpx`)
- Environment-driven credentials/headers:
  - `SYNC_SERVER_URL`
  - `SYNC_SITE_ID`
  - `SYNC_DEVICE_ID`
  - `SYNC_DEVICE_TOKEN`
  - `SYNC_CLIENT_VERSION`
  - `SYNC_SERVER_TIMEOUT`

## Future Architecture
- Expand `apps/documents` into a functional module with same layered conventions
- Add broader integration resilience patterns (retries/circuit breaking) when load grows
- Introduce explicit sync read models/cache only if operationally necessary
