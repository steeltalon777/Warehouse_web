# AI_CONTEXT

## System architecture
Warehouse_web is a Django SSR client application with layered boundaries:
- API/UI layer (urls + views + templates)
- Service layer (`CatalogService`)
- Repository/data access layer (`SyncServerClient` and local ORM)
- Data sources (local DB + external SyncServer DB through API only)

## Backend rules
- Keep business orchestration in `apps/catalog/services.py`
- Keep views thin: request parsing, permission checks, response rendering
- Do not duplicate SyncServer transport logic in views/forms/templates
- Standardize external error translation in service result objects

## Database rules
- Local Django DB is for app-local persistence and auth domain
- Catalog master-data authority is external SyncServer
- Do not add direct write paths to SyncServer-owned data via local ORM
- Preserve UUID-based identity usage in catalog models

## Layered architecture
- **API**: `config/urls.py` + app url modules + view handlers
- **Services**: `apps/catalog/services.py`
- **Repositories**: `apps/integration/syncserver_client.py` and Django ORM access in app models
- **Models**: `apps/catalog/models.py`, `apps/users/models.py`, `apps/client/models.py`, `apps/common/models.py`

## Client rules
- Primary client is browser users (warehouse operators)
- UI uses Django templates (SSR)
- Protected routes require authentication and role checks via shared permission helpers

## Architecture constraints
- SyncServer headers must be present for outbound requests (`X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`)
- SyncServer calls must use bounded timeout (`SYNC_SERVER_TIMEOUT`)
- Catalog workflows should stay aligned with ADR decisions in `docs/adr/`
