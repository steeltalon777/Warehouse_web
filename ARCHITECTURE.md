# ARCHITECTURE

## System Overview
Warehouse_web — модульный Django-монолит с server-side rendering. Он отвечает за UI, авторизацию и ролевой доступ, а мастер-данные каталога запрашивает/изменяет через SyncServer.

## High-Level Architecture
```text
Clients (browser users)
    ↓
API / Application Layer (Django URLs + Views)
    ↓
Service Layer (CatalogService)
    ↓
Repository / Data Layer (SyncServerClient + local Django ORM)
    ↓
Database
  - Local SQLite (Django auth/admin/session + local models)
  - External DB behind SyncServer (catalog source of truth)
```

## Application Layers
### API layer
- `config/urls.py`, `apps/*/urls.py`
- `apps/catalog/views.py`, `apps/client/views.py`

### Service layer
- `apps/catalog/services.py` (оркестрация и унификация обработки ошибок)

### Repository layer
- `apps/integration/syncserver_client.py` (HTTP gateway в SyncServer)
- Django ORM модели в `apps/*/models.py` для локальных данных и совместимости

### Models / entities
- Catalog: `Category`, `Unit`, `Item`
- Users: `Site`, `UserProfile`, `Role`

## Data Model
- Локально в Django: users/profiles/site и прочие служебные данные.
- Каталог (`Category`, `Unit`, `Item`) представлен моделями, но актуальное чтение/запись в UI выполняется через SyncServer API.

## Data Flow
```text
Client → Django View → CatalogService → SyncServerClient → SyncServer API
```

## Architectural Principles
- Разделение UI и бизнес-интеграции: views не работают с HTTP-клиентом напрямую.
- Единая точка интеграции: все внешние запросы через `SyncServerClient`.
- Явная ролевая авторизация (`can_manage_catalog`, `can_use_client`).
- Ошибки интеграции преобразуются в `ServiceResult` для предсказуемого поведения UI.

## External Integrations
- SyncServer HTTP API (`httpx.Client`)
- Заголовки доверенного устройства: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`

## Future Architecture
- Добавление модулей документов/операций склада поверх того же шаблона слоев.
- Потенциальный read-model/cache для ускорения списков без смены source of truth.
