# MEMORY

## Project role
Warehouse_web = Django web-client and UI shell for warehouse operations. SyncServer = source of truth for catalog master-data.

## Architectural decisions
- Catalog CRUD in UI goes through SyncServer HTTP API.
- No direct master-data writes via Django ORM for Category/Unit/Item.
- Single integration client is used for SyncServer communication.

## Integration model
- Django views -> catalog service -> SyncServer client -> SyncServer API.
- Static trusted system device headers are sent on each request.

## Known constraints
- Legacy ORM catalog models may still exist for migration compatibility, but are not source of truth.
- Documents module remains a placeholder.

## Future direction
- Expand SyncServer-driven workflows (stocks, movements, sync events) without shifting source-of-truth responsibility back to Django.
