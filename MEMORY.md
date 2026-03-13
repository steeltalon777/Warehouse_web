# MEMORY

## Invariants

- SyncServer = source of truth для warehouse domain.
- Django = UI + session + thin API client.
- Нет business logic в Django.

## Implemented integration

- Новый слой `apps/sync_client` c service authentication.
- Список операций/остатков работает с `limit/offset`.
- Каталог и root admin страницы используют sync_client слой.
