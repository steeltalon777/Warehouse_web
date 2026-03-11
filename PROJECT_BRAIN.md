# PROJECT_BRAIN

## Project purpose
Warehouse_web — Django SSR-клиент для складской команды: даёт интерфейс, роли и авторизацию; каталог работает через внешний SyncServer.

## Architecture summary
- Layered modular monolith.
- `views` → `CatalogService` → `SyncServerClient`.
- Локальная БД не является главной для мастер-данных каталога.

## Key modules
- `apps/catalog` — каталоговый UI и сервисы
- `apps/integration` — HTTP интеграция с SyncServer
- `apps/users` — роли, site, пользовательский профиль
- `apps/common` — permission rules
- `apps/client` — dashboard

## Key entities
- Catalog: `Category`, `Unit`, `Item`
- Access: `Site`, `UserProfile`, `Role`

## Key services
- `CatalogService`: единая оркестрация вызовов и маппинг ошибок
- `SyncServerClient`: HTTP contract + headers + low-level errors

## Entry points
- `manage.py`
- `config/urls.py`
- `config/asgi.py` / `config/wsgi.py`

## Important constraints
- Не делать прямые master-data write операции через Django ORM как основной путь.
- Для каталога использовать SyncServer endpoints.
- Роли проверяются через `apps.common.permissions`.

## Data flow
`Client → Django View → CatalogService → SyncServerClient → SyncServer`.
