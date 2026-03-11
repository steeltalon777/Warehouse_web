# ARCHITECTURE

## System Overview
Warehouse_web — Django web-клиент складской системы для работы со справочниками и ролевым доступом сотрудников. Система ориентирована на UI-операции и интеграцию с внешним SyncServer API.

## High-Level Architecture
```text
Clients (Browser, Django Admin)
        ↓
API / Application Layer (Django URLs + Views)
        ↓
Service Layer (permissions, integration services)
        ↓
Repository / Data Layer (Django ORM models)
        ↓
Database (SQLite by default)
```

## Application Layers
### API layer
- `config/urls.py` — корневая маршрутизация.
- `apps/*/urls.py` — маршруты модулей.
- `apps/catalog/views.py`, `apps/client/views.py` — обработка HTTP-запросов и рендер шаблонов.

### Service layer
- `apps/common/permissions.py` — правила ролевого доступа.
- `apps/common/services/syncserver_client.py` и `apps/integration/syncserver/client.py` — HTTP-клиенты к SyncServer.

### Repository / data layer
- Django ORM запросы в моделях и view-классах (`select_related`, CRUD через generic views).

### Models / entities
- `apps/catalog/models.py` — `Category`, `Unit`, `Item`.
- `apps/users/models.py` — `Site`, `UserProfile`, `Role`.

## Data Model
Ключевые сущности:
- **Category**: дерево категорий (self-reference `parent`), валидация против циклов.
- **Unit**: справочник единиц измерения (`code` уникален).
- **Item**: номенклатурная позиция, связана с `Category` и `Unit`.
- **Site**: склад/площадка.
- **UserProfile**: расширение пользователя с ролью и привязкой к площадке.

## Data Flow
Типичный сценарий запроса:
1. Client отправляет HTTP-запрос в Django URL.
2. View проверяет аутентификацию и роль через `can_*` функции.
3. View обращается к ORM (или сервису интеграции).
4. ORM читает/пишет данные в БД.
5. View возвращает HTML-шаблон клиенту.

Интеграционный сценарий:
`Client → Django View/Service → SyncServerClient(httpx) → External SyncServer API`.

## Architectural Principles
- Разделение по Django-приложениям (`catalog`, `users`, `client`, `common`, `integration`).
- Ролевой доступ централизован в `apps/common/permissions.py`.
- Использование Django generic views для стандартного CRUD.
- Доменные модели каталога используют UUID как primary key.
- UI-first подход: серверный рендер HTML-шаблонов.

## External Integrations
- **SyncServer API**: внешний backend API через `SYNCSERVER_API_URL`.
- Интеграция выполняется через `httpx.Client`.

## Future Architecture
- Расширение `documents` в полноценный модуль документооборота.
- Выделение явного service layer для бизнес-операций (сейчас часть логики живет во view).
- Консолидация дублей интеграционных клиентов в одном адаптере.
- Потенциальный переход с SQLite на PostgreSQL для production.
