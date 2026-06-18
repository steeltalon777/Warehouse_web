# AI Context

## Role

`Warehouse_web` is the active Django web client, admin UI, session host, and BFF layer for browser features.

## Rules

- SyncServer owns warehouse truth and business validation.
- Django owns web technical state and UI orchestration.
- Do not add local Django ORM models for catalog or other warehouse domain entities.
- Every SyncServer HTTP call must go through `apps/sync_client/`.
- Keep views thin; put multi-step UI workflows in services.
- Do not expose SyncServer tokens to browser JavaScript.
- Angular integration must use Django same-origin BFF endpoints and CSRF.

## Local State

Allowed local state:

- Django auth and sessions.
- SyncServer user binding.
- Technical cache.
- BFF/UI support state.

Not allowed local state:

- Authoritative catalog, operation, balance, document, recipient, user, site, or device domain state.

## Main Work Areas

- `apps/sync_client/` - canonical SyncServer integration.
- `apps/catalog/` - catalog and nomenclature UI/BFF flows.
- `apps/users/` - auth and SyncServer binding.
- `templates/` - SSR pages and host templates.
- `config/settings/` - Django settings.

## Verification

- Run `python manage.py test` after Django changes.
