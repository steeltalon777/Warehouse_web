# INDEX

## Project overview
Django web-клиент для складской системы с SSR-интерфейсом и ролями доступа.

## Architecture overview
- Модульный монолит Django.
- Каталог проксируется в SyncServer (источник истины).
- Поток: Browser → Django Views → Service → SyncServerClient → SyncServer.

## Tech stack
- Python 3, Django 6, Django Templates, httpx, SQLite.

## Application structure
- `config/` — конфигурация приложения и корневой роутинг.
- `apps/catalog/` — каталог (UI + service + формы).
- `apps/integration/` — внешний API клиент.
- `apps/users/` — пользовательские профили и роли.
- `apps/common/` — permissions.
- `apps/client/` — dashboard.
- `apps/documents/` — placeholder.

## Main modules
- Catalog module
- Users & roles module
- Integration module
- Client dashboard module

## Entry points
- `manage.py`
- `config/settings.py`
- `config/urls.py`
- `config/asgi.py`, `config/wsgi.py`

## Important models
- `apps/catalog/models.py`: `Category`, `Unit`, `Item`
- `apps/users/models.py`: `Site`, `UserProfile`, `Role`

## Important services
- `apps/catalog/services.py`: `CatalogService`, `ServiceResult`
- `apps/integration/syncserver_client.py`: `SyncServerClient`

## Future modules
- Развитие `apps/documents`
- Расширение складских сценариев (движения/остатки) через SyncServer API

## Architecture decisions
- ADR: `docs/adr/0001-django-modular-monolith.md`
- ADR: `docs/adr/0005-syncserver-http-integration.md`
- ADR: `docs/adr/0006-syncserver-source-of-truth-catalog.md`
- ADR: `docs/adr/0009-no-direct-master-data-writes-via-django-orm.md`
