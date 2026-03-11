# MEMORY

## System architecture
- Django modular monolith with server-rendered templates.
- Warehouse_web acts as client; SyncServer owns catalog truth.
- Integration boundary is HTTP (`SyncServerClient`).

## Core entities
- Catalog: `Category`, `Unit`, `Item`.
- Access domain: `Site`, `UserProfile`, `Role`.

## Data model decisions
- UUID identifiers for domain entities.
- Category supports parent-child hierarchy.
- User profile extends Django user via OneToOne.
- Catalog models exist locally, but runtime authority is external SyncServer.

## API design
- Internal endpoints are Django routes (`/catalog/*`, `/client/*`, `/users/*`).
- External calls are centralized in integration client.
- Required trusted headers identify site/device/client version.

## Business rules
- Catalog management requires elevated roles.
- Dashboard and catalog pages are protected by auth + role checks.
- Integration errors are surfaced to UI through service-layer mapping.

## Known pitfalls
- Production settings hardening is incomplete (debug/secret/hosts defaults in code).
- No Docker/Gunicorn assets in repository at this stage.
- Static collection path (`STATIC_ROOT`) is not configured yet.
- Catalog availability depends on SyncServer uptime and bootstrap identifiers.

## Future architecture
- Introduce explicit dev/prod settings split.
- Add deployment runtime artifacts and static pipeline hardening.
- Expand documents/warehouse workflow modules without breaking SyncServer boundary.
