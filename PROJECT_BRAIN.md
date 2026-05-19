# PROJECT_BRAIN

## Strategic Direction

1. Django remains the active web/admin client and BFF.
2. SyncServer owns domain truth.
3. Angular nomenclature runs through Django and same-origin BFF endpoints.

## Implemented Direction

- Root/admin panel for users, roles, and sites goes through SyncServer API.
- Chief/storekeeper UI uses the shared SyncServer client layer.
- Catalog app uses services and SyncServer APIs, not local catalog ORM.

## Next Steps

- Add Django BFF endpoints for Angular nomenclature.
- Convert `Warehouse_frontend` into an Angular workspace.
- Expand tests around SyncServer client wrappers and BFF responses.
