# INDEX

## Project overview
- Django web-client для SyncServer.
- SyncServer — источник истины каталога.

## Architecture overview
- См. `ARCHITECTURE.md`.
- Ключевая связь: Warehouse_web → HTTP → SyncServer.

## Tech stack
- Django 6, Python 3, httpx, Django templates.

## Main apps/modules
- `apps/catalog` — catalog UI + forms + services.
- `apps/integration` — HTTP client SyncServer.
- `apps/users` — auth/roles.
- `apps/common` — permissions/shared.

## Entry points
- `manage.py`, `config/urls.py`, `config/settings.py`.

## Integration points
- `apps/integration/syncserver_client.py`
- `apps/catalog/services.py`

## Important views/forms/services
- Views: `apps/catalog/views.py`
- Forms: `apps/catalog/forms.py`
- Services: `apps/catalog/services.py`

## Architecture decisions
- ADRs: `docs/adr/0005-syncserver-http-integration.md`, `docs/adr/0006-*.md ...`
