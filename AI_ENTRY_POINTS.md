# AI_ENTRY_POINTS

## Server entrypoints
- `manage.py` — CLI entrypoint Django.
- `config/wsgi.py` — WSGI entrypoint.
- `config/asgi.py` — ASGI entrypoint.

## API layer (HTTP endpoints)
- Root router: `config/urls.py`
- Catalog endpoints: `apps/catalog/urls.py`
- User auth endpoints: `apps/users/urls.py`
- Client dashboard endpoint: `apps/client/urls.py`
- Documents endpoint namespace (пустой): `apps/documents/urls.py`

## Service layer
- `apps/catalog/services.py` (`CatalogService`)

## Repository / Data layer
- External integration: `apps/integration/syncserver_client.py`
- Local ORM models: `apps/catalog/models.py`, `apps/users/models.py`

## Models / Entities
- Catalog: `Category`, `Unit`, `Item`
- Access/User: `Site`, `UserProfile`, `Role`

## Configuration
- `config/settings.py`
- Key integration env vars:
  - `SYNC_SERVER_URL`
  - `SYNC_SITE_ID`
  - `SYNC_DEVICE_ID`
  - `SYNC_DEVICE_TOKEN`
  - `SYNC_CLIENT_VERSION`
  - `SYNC_SERVER_TIMEOUT`
