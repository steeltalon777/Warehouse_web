# Warehouse_web

Warehouse_web is a Django server-rendered web client for SyncServer. SyncServer owns warehouse domain data and business rules. Django provides the web UI, session handling, admin workflows, and HTTP integration.

## Project Overview

- Django is a web client, not a second warehouse backend.
- SyncServer is the source of truth for sites, catalog data, access scopes, balances, operations, and user sync state.
- Django stores only technical local state: auth users, sessions, `SyncUserBinding`, and a transitional mirror of sites for admin convenience.

## Architecture Overview

High-level request flow:

`Browser -> Django views/forms/admin -> app services -> apps/sync_client -> SyncServer API`

Key rules:

- business rules stay in SyncServer
- Django views remain thin
- SyncServer API access is centralized in `apps/sync_client`
- root-managed users and sites are administered through Django admin

## Tech Stack

- Python 3.12+
- Django 5.2
- httpx
- WhiteNoise
- Gunicorn
- SQLite by default, PostgreSQL via environment settings
- Docker / docker-compose

## Project Structure

```text
config/              Django settings, URL routing, ASGI/WSGI entrypoints
apps/users/          local auth integration, SyncUserBinding, Django-admin sync flows
apps/sync_client/    canonical SyncServer HTTP clients and API wrappers
apps/catalog/        SSR catalog screens for categories, units, items
apps/operations/     SSR operations screens
apps/balances/       SSR balances screens
apps/client/         dashboard and working pages
apps/admin_panel/    root-only device and access screens
apps/common/         shared permissions, mixins, error handling, health checks
templates/           Django templates
static/              CSS and static assets
docs/                ADRs, reports, supporting documentation
```

## Installation / Setup

1. Create and activate a virtual environment.
2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create `.env` and configure at least:

- `SECRET_KEY`
- `DEBUG`
- `SYNC_SERVER_URL` (must include `/api/v1`)
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- database settings if not using SQLite

4. Apply migrations.

```bash
python manage.py migrate
```

## Running the Project

Development:

```bash
python manage.py runserver
```

Docker:

```bash
docker compose up --build
```

## Main Modules

- `apps/users`
  - local Django auth integration
  - `SyncUserBinding` for per-user SyncServer identity and token storage
  - Django-admin flows for SyncServer-backed user and site management
- `apps/sync_client`
  - canonical runtime client
  - root admin client
  - catalog, balances, operations, access, and admin API wrappers
- `apps/catalog`
  - categories, units, and items screens
  - categories use a tree-first UI backed by SyncServer
- `apps/operations`
  - operations list, detail, and creation screens
- `apps/balances`
  - balances and by-site views
- `apps/admin_panel`
  - root-only device and access pages

## API Overview

Warehouse_web does not expose its own warehouse domain API. It consumes SyncServer APIs, including:

- auth and sync identity endpoints
- root admin endpoints for users, sites, scopes, devices, and token rotation
- catalog endpoints for categories, items, and units
- operations endpoints
- balances endpoints

## Important Notes

- superuser/root flows use `SYNC_ROOT_USER_TOKEN`
- non-root runtime flows use per-user tokens from `SyncUserBinding`
- catalog master data is API-driven; local catalog ORM models are legacy-only and not the source of truth
- sites are mirrored locally only as an admin cache during transition

## Related Docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [INDEX.md](INDEX.md)
- [AI_CONTEXT.md](AI_CONTEXT.md)
- [AI_ENTRY_POINTS.md](AI_ENTRY_POINTS.md)
- [MEMORY.md](MEMORY.md)
- [docs/adr/](docs/adr/)
