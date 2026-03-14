# MEMORY

## Invariants

- SyncServer = source of truth для warehouse domain.
- Django = SSR UI + session + thin API client.
- Нет бизнес-логики склада и direct domain writes в Django ORM.

## Implemented integration

- Canonical слой `apps/sync_client` с service auth + acting context headers.
- Operations/Balances SSR list pages поддерживают `search/limit/offset`.
- Operations SSR create/detail используют `OperationsAPI.create/get`.
- Catalog SSR pages (items/categories/units) работают через `CatalogService` + `CatalogAPI`.
- Root admin SSR pages используют `AdminAPI`: users/sites/devices/access + site/device create/edit.

## Next phase (не в этом этапе)

- UI/UX polish (тексты, layout, визуальный стиль, навигационные улучшения).
- Дополнительные сценарии edit/submit/cancel операций при необходимости UX этапа.
