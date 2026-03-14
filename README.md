# Warehouse_web

Warehouse_web — Django SSR web-клиент для SyncServer. Вся бизнес-логика складской системы и domain-данные принадлежат SyncServer.

## Архитектура

`Django SSR pages/forms -> apps.sync_client -> SyncServer API`

- Django отвечает за web UI, сессии, рендеринг страниц и UX-права по ролям.
- Django **не** хранит и не исполняет бизнес-логику склада.
- Все HTTP-вызовы к SyncServer централизованы в `apps/sync_client/*`.

## Ключевые настройки

- `SYNC_SERVER_URL` (обязательно с `/api/v1`)
- `SYNC_SERVER_SERVICE_TOKEN`
- `SYNC_SERVER_TIMEOUT`

Для каждого запроса Django передаёт service token + acting context headers (`X-Acting-User-Id`, `X-Acting-Site-Id`).

> Legacy device auth (`SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`) не используется в новом SSR слое.

## SSR coverage (текущий этап)

- `apps/operations`: `/operations/`, `/operations/create/`, `/operations/<id>/`
- `apps/balances`: `/balances/`, `/balances/by-site/`
- `apps/catalog`: items/categories/units list/create/edit + category tree
- `apps/admin_panel`: users/sites/devices/access + site/device create/edit

## Приложения

- `apps/users` — login/logout
- `apps/client` — dashboard/legacy entry points
- `apps/operations` — операции (SSR)
- `apps/balances` — остатки (SSR)
- `apps/catalog` — ТМЦ/категории/единицы (SSR)
- `apps/admin_panel` — root administration (SSR)
- `apps/sync_client` — canonical thin API client layer
