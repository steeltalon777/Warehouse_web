# INDEX

## Project overview
Warehouse_web — Django web-клиент складской системы с UI для пользователей склада, ролями доступа и модулями справочников.

## Architecture overview
Многомодульный Django-проект (MVT): URLs/Views → permissions/services → ORM models → SQLite, с внешней интеграцией в SyncServer API.

## Tech stack
- Python 3
- Django 6
- Django Templates
- Django ORM
- SQLite
- httpx

## Application structure
- `config/` — настройки проекта и корневые URL.
- `apps/catalog/` — категории, единицы, номенклатура.
- `apps/users/` — роли, профили, login/logout, сигналы.
- `apps/client/` — dashboard.
- `apps/common/` — permissions и общие сервисы.
- `apps/integration/` — клиент внешнего SyncServer.
- `apps/documents/` — будущий модуль документов.

## Main modules
- Catalog management
- User roles and access control
- Client dashboard
- External sync integration

## Entry points
- `manage.py`
- `config/settings.py`
- `config/urls.py`
- `config/asgi.py`
- `config/wsgi.py`

## Important models
- `apps/catalog/models.py`: `Category`, `Unit`, `Item`
- `apps/users/models.py`: `Site`, `UserProfile`, `Role`

## Important services
- `apps/common/permissions.py` — RBAC rules
- `apps/common/services/syncserver_client.py` — SyncServer client
- `apps/integration/syncserver/client.py` — SyncServer client (integration namespace)

## Future modules
- Документы (`apps/documents`)
- Расширение интеграций и синхронизации
- Операционный контур склада (остатки, операции)

## Architecture decisions
- `docs/adr/0001-django-modular-monolith.md`
- `docs/adr/0002-uuid-domain-identifiers.md`
- `docs/adr/0003-role-based-access-via-userprofile.md`
- `docs/adr/0004-server-rendered-ui.md`
- `docs/adr/0005-syncserver-http-integration.md`
