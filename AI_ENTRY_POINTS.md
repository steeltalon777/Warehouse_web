# AI_ENTRY_POINTS

## Server entrypoints
- `manage.py` — Django management and local runtime entrypoint
- `config/wsgi.py` — WSGI application entrypoint
- `config/asgi.py` — ASGI application entrypoint
- `config/settings/__init__.py` — environment switch (`development`/`production`)

## API layer
- `config/urls.py` — root route composition
- `apps/catalog/urls.py` — catalog pages/actions
- `apps/users/urls.py` — login/logout
- `apps/client/urls.py` — dashboard
- `apps/documents/urls.py` — documents namespace placeholder

## Service layer
- `apps/catalog/services.py` — catalog use cases + error normalization

## Repository / Data layer
- `apps/integration/syncserver_client.py` — external SyncServer HTTP client
- `apps/*/models.py` — local data models for Django ORM

## Models / Entities
- `apps/catalog/models.py`: `Category`, `Unit`, `Item`
- `apps/users/models.py`: `Site`, `UserProfile`, `Role`

## Configuration
- `config/settings/base.py`
- `config/settings/development.py`
- `config/settings/production.py`
- `.env` variables for integration and DB/runtime settings
