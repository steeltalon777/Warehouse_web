# INDEX

## Project overview
Django server-rendered warehouse client with role-based access and SyncServer integration.

## Architecture overview
- Layered modular monolith.
- Browser UI served by Django templates.
- Catalog data path: Django → SyncServer API → SyncServer DB.

## Tech stack
- Python 3
- Django 6
- Django Templates
- httpx
- python-dotenv
- SQLite (local default)

## Application structure
- `config/` — settings and root wiring.
- `apps/catalog/` — catalog UI, forms, service layer.
- `apps/integration/` — SyncServer HTTP client.
- `apps/users/` — profiles, roles, auth pages.
- `apps/common/` — permissions/helpers.
- `apps/client/` — dashboard.
- `apps/documents/` — scaffold.
- `templates/` — SSR templates.

## Main modules
- Catalog module
- Users & role access module
- Integration module
- Client dashboard module

## Entry points
- `manage.py`
- `config/settings.py`
- `config/urls.py`
- `config/wsgi.py`
- `config/asgi.py`

## Important models
- `apps/catalog/models.py`: `Category`, `Unit`, `Item`
- `apps/users/models.py`: `Site`, `UserProfile`, `Role`

## Important services
- `apps/catalog/services.py`: service orchestration and error mapping
- `apps/integration/syncserver_client.py`: external API gateway

## Future modules
- `apps/documents` functional expansion
- Additional warehouse workflows over SyncServer API

## Architecture decisions
- `docs/adr/0001-django-modular-monolith.md`
- `docs/adr/0002-uuid-domain-identifiers.md`
- `docs/adr/0003-role-based-access-via-userprofile.md`
- `docs/adr/0004-server-rendered-ui.md`
- `docs/adr/0005-syncserver-http-integration.md`
- `docs/adr/0006-syncserver-source-of-truth-catalog.md`
- `docs/adr/0007-warehouse-web-http-client-role.md`
- `docs/adr/0008-catalog-integration-via-service-layer.md`
- `docs/adr/0009-no-direct-master-data-writes-via-django-orm.md`
