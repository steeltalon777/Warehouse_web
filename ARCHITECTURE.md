# ARCHITECTURE

## System Overview
Warehouse_web — frontend-like Django web-client для операторов склада. Master-data живут в SyncServer.

## Role of Warehouse_web
- UI / templates / forms
- authentication, users, roles
- вызовы SyncServer API для каталога

## Role of SyncServer
- source of truth по `Category`, `Unit`, `Item`
- admin write endpoints и read/sync endpoints
- device-based authentication

## High-Level Architecture
```text
Warehouse_web
  ↓ HTTP
SyncServer
  ↓
PostgreSQL
```

## Application Layers
### UI Layer
`templates/*`, `apps/catalog/views.py`, `apps/users/*`

### Integration Layer
`apps/integration/syncserver_client.py`, `apps/catalog/services.py`

### Local Django Data
Локальная БД используется для Django concern-ов (users, sessions, admin). Каталог не является локальной истиной.

## Architectural Constraints
- Нельзя писать master-data каталога напрямую через Django ORM.
- Любое создание/изменение Category/Unit/Item — только через SyncServer API.
- Ошибки SyncServer маппятся в user-friendly сообщения (400/404/409/5xx).

## Future Evolution
- Возможный cache/read model для ускорения UI без смены source of truth.
- Расширение на остатки и движения после появления API в SyncServer.
