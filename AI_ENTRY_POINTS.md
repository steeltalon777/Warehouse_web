# AI_ENTRY_POINTS

## Server entrypoints
- `manage.py` — Django CLI entrypoint.
- `config/wsgi.py` — WSGI entrypoint.
- `config/asgi.py` — ASGI entrypoint.

## API layer
- `config/urls.py` — root route composition.
- `apps/catalog/urls.py` — catalog endpoints.
- `apps/users/urls.py` — auth/user endpoints.
- `apps/client/urls.py` — dashboard endpoints.
- `apps/documents/urls.py` — documents namespace.

## Service layer
- `apps/catalog/services.py` — `CatalogService`, `ServiceResult`.

## Repository / Data layer
- `apps/integration/syncserver_client.py` — SyncServer HTTP gateway.
- `apps/*/models.py` — local persistence models.

## Models / Entities
- Catalog: `Category`, `Unit`, `Item`.
- Users/access: `Site`, `UserProfile`, `Role`.

## Configuration
- `config/settings.py`.
- Environment-driven integration keys:
  - `SYNC_SERVER_URL`
  - `SYNC_SITE_ID`
  - `SYNC_DEVICE_ID`
  - `SYNC_DEVICE_TOKEN`
  - `SYNC_CLIENT_VERSION`
  - `SYNC_SERVER_TIMEOUT`
