# AI_ENTRY_POINTS

## Server entrypoints
- `manage.py` — основной CLI/entrypoint Django.
- `config/asgi.py` — ASGI entrypoint.
- `config/wsgi.py` — WSGI entrypoint.

## API layer
- `config/urls.py` — root URL router.
- `apps/catalog/urls.py` + `apps/catalog/views.py` — каталог и CRUD.
- `apps/client/urls.py` + `apps/client/views.py` — dashboard.
- `apps/users/urls.py` — auth endpoints (login/logout).
- `apps/documents/urls.py` — placeholder для документов.

## Service layer
- `apps/common/permissions.py` — проверка ролей и прав доступа.
- `apps/common/services/syncserver_client.py` — HTTP-сервис SyncServer.
- `apps/integration/syncserver/client.py` — интеграционный клиент SyncServer.

## Repository / Data layer
- ORM доступ через модели:
  - `apps/catalog/models.py`
  - `apps/users/models.py`
- ORM вызовы в view-классах (`ListView/CreateView/UpdateView/DeleteView`).

## Models / Entities
- Catalog: `Category`, `Unit`, `Item`
- Users: `Site`, `UserProfile`, `Role`

## Configuration
- `config/settings.py` — INSTALLED_APPS, DATABASES, templates, static, `SYNCSERVER_API_URL`.
- `config/__init__.py` — package marker.
