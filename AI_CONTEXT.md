# AI_CONTEXT

- Warehouse_web — только web client для SyncServer.
- Любой новый API-вызов добавлять только в `apps/sync_client`.
- Views использовать class-based подход.
- В запросах к SyncServer всегда передавать service auth + acting user/site headers.
- `active_site` хранить в сессии (`request.session["active_site"]`).
