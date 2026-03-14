# AI_CONTEXT

- Warehouse_web — только SSR web client для SyncServer.
- Любой новый API-вызов добавлять только в `apps/sync_client` (или тонкий adapter над ним).
- Views должны оставаться thin, без raw requests.
- В запросах к SyncServer всегда передавать service auth + acting user/site headers.
- `active_site` брать из `request.session["active_site"]` (с fallback на профиль).
- Не использовать legacy device auth переменные (`SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`).
