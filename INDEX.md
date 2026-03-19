# Index

## Project Overview

Warehouse_web is a Django server-rendered web client for SyncServer. SyncServer owns warehouse domain data and rules. Django owns UI, sessions, admin tooling, and integration orchestration.

## Architecture Overview

- browser requests are handled by Django SSR views and Django admin
- app services orchestrate multi-step flows
- `apps/sync_client` owns HTTP communication with SyncServer
- SyncServer remains the source of truth for warehouse domain data

## Tech Stack

- Python 3.12+
- Django 5.2
- httpx
- WhiteNoise
- Gunicorn
- SQLite / PostgreSQL
- Docker

## Application Structure

- `config/` - settings, URLs, ASGI/WSGI
- `apps/users/` - auth, sync binding, admin sync workflows
- `apps/sync_client/` - canonical client layer
- `apps/catalog/` - categories, units, items screens
- `apps/operations/` - operations screens
- `apps/balances/` - balances screens
- `apps/client/` - dashboard and working pages
- `apps/admin_panel/` - devices and access
- `apps/common/` - shared helpers, permissions, mixins

## Main Modules

- `apps/users`
- `apps/sync_client`
- `apps/catalog`
- `apps/operations`
- `apps/balances`
- `apps/client`
- `apps/admin_panel`

## Entry Points

- `manage.py`
- `config/urls.py`
- `config/wsgi.py`
- `config/asgi.py`
- `apps/users/admin.py`

## Important Models

- `django.contrib.auth.models.User`
- `apps.users.models.SyncUserBinding`
- `apps.users.models.Site`
- `apps.users.models.UserProfile` as a deprecated compatibility tail

## Important Services

- `apps.users.services.UserSyncService`
- `apps.users.services.SiteSyncService`
- `apps.catalog.services.CatalogService`
- `apps.client.services.DomainService`
- `apps.sync_client.client.SyncServerClient`
- `apps.sync_client.root_admin_client.SyncServerRootAdminClient`

## Future Modules

- full API-driven units and items polish
- further removal of deprecated local catalog/state tails
- stronger smoke and runtime validation against SyncServer

## Architecture Decisions

- [ADR-0001](docs/adr/0001-django-as-syncserver-web-client.md)
- [ADR-0002](docs/adr/0002-syncserver-as-source-of-truth.md)
- [ADR-0003](docs/adr/0003-centralized-syncserver-client-layer.md)
- [ADR-0004](docs/adr/0004-django-admin-for-root-management.md)
- [ADR-0005](docs/adr/0005-sync-user-binding-for-user-tokens.md)
- [ADR-0006](docs/adr/0006-no-local-master-data-ownership.md)
