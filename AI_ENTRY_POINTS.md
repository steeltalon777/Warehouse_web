# AI_ENTRY_POINTS

## Django entry points
- `manage.py`
- `config/wsgi.py`
- `config/asgi.py`

## URLs
- `config/urls.py`
- `apps/catalog/urls.py`
- `apps/users/urls.py`
- `apps/client/urls.py`

## Catalog module
- Views: `apps/catalog/views.py`
- Forms: `apps/catalog/forms.py`
- Services: `apps/catalog/services.py`
- Templates: `templates/catalog/*`

## Integration client
- `apps/integration/syncserver_client.py` (single source for SyncServer HTTP calls)

## Settings
- `config/settings.py` (`SYNC_SERVER_URL`, `SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`, `SYNC_CLIENT_VERSION`)
