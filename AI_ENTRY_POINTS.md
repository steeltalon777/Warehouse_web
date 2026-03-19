# AI Entry Points

## Server Entrypoints

- `manage.py` - Django CLI entrypoint
- `config/wsgi.py` - WSGI entrypoint for Gunicorn
- `config/asgi.py` - ASGI entrypoint
- `config/urls.py` - top-level URL routing

## API Layer

- `apps/catalog/views.py`
- `apps/client/views.py`
- `apps/operations/views.py`
- `apps/balances/views.py`
- `apps/admin_panel/views.py`
- `apps/users/admin.py`

## Service Layer

- `apps/users/services.py`
- `apps/catalog/services.py`
- `apps/client/services.py`

## Repository / Data Layer

- `apps/sync_client/client.py`
- `apps/sync_client/root_admin_client.py`
- `apps/sync_client/catalog_api.py`
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`
- `apps/sync_client/access_api.py`
- `apps/sync_client/admin_api.py`
- `apps/sync_client/auth_api.py`
- `apps/sync_client/session_auth.py`

## Models / Entities

- `apps/users/models.py`
- `apps/catalog/models.py` as legacy local ORM tail

## Configuration

- `config/settings/base.py`
- `config/settings/development.py`
- `config/settings/production.py`
- `.env.example`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
