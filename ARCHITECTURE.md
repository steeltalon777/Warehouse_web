# Architecture

## System Overview

`Warehouse_web` is the active Django web client for SyncServer. It provides browser UI, Django admin, sessions, user binding, and same-origin BFF endpoints for Angular features.

SyncServer owns warehouse domain data and business rules. Django does not own catalog, operations, balances, users, sites, devices, or access scopes as warehouse truth.

## Runtime Flow

```text
Browser
  -> Django views/admin/BFF
    -> app service
      -> apps/sync_client wrapper
        -> SyncServer /api/v1
```

For Angular nomenclature:

```text
Browser
  -> Django /nomenclature/
    -> Angular shell assets from Warehouse_frontend
      -> Django /nomenclature/api/*
        -> apps/sync_client
          -> SyncServer
```

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| Routing/views | `config/urls.py`, `apps/*/views.py` | Requests, forms, templates, BFF responses |
| Services | `apps/*/services.py` | UI orchestration and SyncServer-backed workflows |
| Sync client | `apps/sync_client/` | HTTP transport, headers, errors, endpoint wrappers |
| Local models | `apps/users/models.py`, `apps/catalog_cache/models.py` | Technical web state and cache only |
| Templates/static | `templates/`, `static/` | SSR and static assets |

## Local Persistence

Django local DB stores technical web state:

- Django auth users and sessions.
- `SyncUserBinding` for Django user to SyncServer identity/token binding.
- Local site/admin helper state where still needed by web flows.
- Catalog cache for UX/search support.

Catalog master data is not modeled locally in `apps/catalog`. The catalog app works through services and SyncServer APIs.

## Rules

- All SyncServer calls go through `apps/sync_client/`.
- Views should stay thin and delegate multi-step work to services.
- Browser JSON APIs must not expose SyncServer tokens.
- Angular must use Django auth, CSRF, and same-origin BFF endpoints.
- Business validation remains in SyncServer.

## Verification

- Run `python manage.py test` after changes.
- When changing `apps/sync_client/`, verify the affected views or BFF endpoints.
