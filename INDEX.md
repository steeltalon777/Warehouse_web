# INDEX

## Project overview
Warehouse_web is a Django server-rendered warehouse client focused on operator workflows, role-based access, and integration with SyncServer for catalog master data.

## Architecture overview
- Modular monolith on Django apps
- Layered flow: Views -> Services -> Integration client -> External API
- SyncServer is source of truth for catalog domain data

## Tech stack
- Python, Django, Django Templates
- httpx, python-dotenv
- Gunicorn + WhiteNoise
- SQLite/PostgreSQL (via Django DB settings)

## Application structure
- `config/` — settings + root routing + server entrypoints
- `apps/catalog/` — catalog flows
- `apps/integration/` — external API gateway
- `apps/users/` — user profile and roles
- `apps/common/` — shared permissions + health endpoints
- `apps/client/` — dashboard
- `apps/documents/` — module scaffold
- `templates/` — SSR pages

## Main modules
- Catalog management
- Access control and profiles
- Dashboard/client area
- SyncServer integration

## Entry points
- `manage.py`
- `config/urls.py`
- `config/wsgi.py`
- `config/asgi.py`
- `config/settings/__init__.py`

## Important models
- `apps/catalog/models.py`: `Category`, `Unit`, `Item`
- `apps/users/models.py`: `Site`, `UserProfile`, `Role`

## Important services
- `apps/catalog/services.py`: orchestration and error mapping
- `apps/integration/syncserver_client.py`: HTTP transport and protocol mapping

## Future modules
- Functional expansion of `apps/documents`
- Additional warehouse workflows integrated through SyncServer APIs

## Architecture decisions
- `docs/adr/0001-django-modular-monolith.md`
- `docs/adr/0003-role-based-access-via-userprofile.md`
- `docs/adr/0004-server-rendered-ui.md`
- `docs/adr/0005-syncserver-http-integration.md`
- `docs/adr/0006-syncserver-source-of-truth-catalog.md`
- `docs/adr/0008-catalog-integration-via-service-layer.md`
