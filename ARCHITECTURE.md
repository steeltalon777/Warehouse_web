# ARCHITECTURE

## System

SyncServer (FastAPI) — backend-владелец domain.
Django (Warehouse_web) — web client + thin API client.

## Request flow

View (CBV) -> service/view logic -> `apps.sync_client` -> SyncServer.

Запрещено:
- HTTP-вызовы из views напрямую;
- дублирование API-кода по приложениям;
- бизнес-правила склада в Django.

## Sync client layer

- `client.py` — базовый `SyncServerClient` (get/post/patch + service auth headers)
- `operations_api.py`
- `balances_api.py`
- `catalog_api.py`
- `admin_api.py`
- `exceptions.py`

## Pages / roles

- `root`: admin panel (`/admin-panel/*`), dashboard
- `chief_storekeeper`: catalog + operations + balances
- `storekeeper`: operations + balances + catalog read/create flows

UI скрывает недоступные элементы, окончательная авторизация — на SyncServer.
