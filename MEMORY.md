# Memory

## Stable Facts

- `Warehouse_web` is the active Django web client and BFF for SyncServer.
- SyncServer owns warehouse domain truth and business validation.
- Django owns sessions, admin UI, SyncServer binding, cache, and BFF/UI orchestration.
- Catalog data is SyncServer-backed through `apps/sync_client/` and services.
- Angular nomenclature work must be hosted by Django and must call Django BFF endpoints.

## Rules

- Do not add local Django ORM models for warehouse catalog/domain entities.
- Do not expose SyncServer tokens to browser JavaScript.
- Do not put warehouse business rules in Django models.
- Keep `apps/sync_client/` as the only SyncServer HTTP layer.

## Verification

- Run `python manage.py test` after changes.
