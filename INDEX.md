# Index

## Project Overview

`Warehouse_web` is the active Django web client and BFF for SyncServer.

## Structure

- `config/` - settings, URLs, ASGI/WSGI.
- `apps/sync_client/` - canonical SyncServer HTTP layer.
- `apps/users/` - auth, user binding, admin sync workflows.
- `apps/catalog/` - catalog/nomenclature UI and BFF work.
- `apps/catalog_cache/` - technical catalog cache.
- `apps/operations/` - operations UI.
- `apps/balances/` - balances UI.
- `apps/client/` - dashboard and working pages.
- `apps/admin_panel/` - admin screens.
- `apps/common/` - shared helpers, permissions, mixins.
- `templates/` - Django templates.
- `static/` - static assets.

## Important Services

- `apps.users.services.UserSyncService`
- `apps.users.services.SiteSyncService`
- `apps.catalog.services.CatalogService`
- `apps.client.services.DomainService`
- `apps.sync_client.client.SyncServerClient`
- `apps.sync_client.root_admin_client.SyncServerRootAdminClient`

## Technical Models

- `django.contrib.auth.models.User`
- `apps.users.models.SyncUserBinding`
- `apps.users.models.Site`
- `apps.catalog_cache.models.CatalogCacheItem`

## Active Direction

- Keep Django as web session host and BFF.
- Build Angular nomenclature shell through Django.
- Keep all catalog/domain data SyncServer-backed.
- Strengthen tests around BFF endpoints and SyncServer client wrappers.

## Verification

- `python manage.py test`
