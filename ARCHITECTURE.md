# ARCHITECTURE

## System

SyncServer (FastAPI) — backend-владелец domain.
Django (Warehouse_web) — SSR web client + thin API client.

## Request flow

View/Form (CBV/FBV) -> `apps.sync_client.*` (или тонкий adapter над ним) -> SyncServer.

Запрещено:
- raw HTTP-вызовы из views;
- дублирование API-кода по приложениям;
- бизнес-правила склада в Django.

## Canonical sync client layer

- `apps/sync_client/client.py` — базовый `SyncServerClient` (get/post/patch + service auth + acting headers)
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`
- `apps/sync_client/catalog_api.py`
- `apps/sync_client/admin_api.py`
- `apps/sync_client/exceptions.py`

## SSR page map

- Operations: list/create/detail
- Balances: list/by-site
- Catalog: items/categories/units list/create/edit + categories tree
- Root admin: users/sites/devices/access, create/edit site/device

## Roles

- `observer`: read-only
- `storekeeper`: operations + balances (и разрешённые read-only каталога)
- `chief_storekeeper`: operations + balances + catalog create/edit
- `root`: полный доступ, включая `/admin-panel/*`

Финальная permission проверка всегда на стороне SyncServer.
