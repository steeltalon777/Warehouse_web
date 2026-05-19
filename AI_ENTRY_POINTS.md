# AI Entry Points

## Server

- `manage.py` - Django CLI.
- `config/urls.py` - root URL routing.
- `config/wsgi.py` - WSGI entry point.
- `config/asgi.py` - ASGI entry point.

## Web And BFF Layer

- `apps/catalog/views.py` - catalog/nomenclature views and BFF candidates.
- `apps/catalog/services.py` - SyncServer-backed catalog orchestration.
- `apps/users/admin.py` - Django admin integration.
- `apps/users/services.py` - user/site sync orchestration.
- `apps/operations/views.py` and `apps/operations/services.py` - operation UI.
- `apps/balances/views.py` - balance UI.

## SyncServer Client Layer

- `apps/sync_client/client.py`
- `apps/sync_client/catalog_api.py`
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`
- `apps/sync_client/admin_api.py`
- `apps/sync_client/auth_api.py`
- `apps/sync_client/session_auth.py`
- `apps/sync_client/root_admin_client.py`

## Technical Models

- `apps/users/models.py`
- `apps/catalog_cache/models.py`

## Tests

- `apps/*/tests.py`
