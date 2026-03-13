# Warehouse_web

Warehouse_web — Django SSR web-клиент для SyncServer. Вся бизнес-логика складской системы и domain-данные принадлежат SyncServer.

## Архитектура

`Django UI -> apps.sync_client -> SyncServer API`

- Django отвечает за web UI, сессии, рендеринг страниц и UX-права по ролям.
- Django **не** хранит и не исполняет бизнес-логику склада.
- Все HTTP-вызовы к SyncServer централизованы в `apps/sync_client/*`.

## Ключевые настройки

- `SYNC_SERVER_URL`
- `SYNC_SERVER_SERVICE_TOKEN`
- `SYNC_SERVER_TIMEOUT`

Для каждого запроса Django передаёт:

- `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`
- `X-Acting-User-Id`
- `X-Acting-Site-Id`

`X-Acting-Site-Id` берётся из `request.session["active_site"]` (с fallback).

## Приложения

- `apps/users` — login/logout
- `apps/client` — dashboard
- `apps/operations` — список, создание, карточка операции
- `apps/balances` — остатки, остатки по складам
- `apps/catalog` — ТМЦ/категории/единицы
- `apps/admin_panel` — root: sites/devices/access
- `apps/sync_client` — thin API client слой
