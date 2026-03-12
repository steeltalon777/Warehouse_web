# AI_ENTRY_POINTS

## Runtime entrypoints
- `manage.py`
- `config/wsgi.py`
- `config/asgi.py`
- `config/settings/__init__.py`

## Architecture-critical entrypoints
- `apps/catalog/services.py` — orchestration boundary for catalog use-cases
- `apps/integration/syncserver_client.py` — external API transport
- `apps/common/permissions.py` — auth access checks (must tolerate missing legacy profile table)
- `apps/users/apps.py` — legacy signals should not be auto-wired into auth flow

## Legacy transition files
- `apps/users/models.py` (`UserProfile`, `Site`, `Role`) — deprecated transitional layer
- `apps/users/signals.py` — deprecated signal logic, intentionally not auto-registered
