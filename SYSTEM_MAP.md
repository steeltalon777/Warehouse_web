# SYSTEM_MAP

## System components

### Clients
- Browser users (storekeeper/chief_storekeeper/root)

### This project
- Warehouse_web (Django SSR web-client)
  - UI + auth + role checks
  - orchestration of catalog operations

### External backend service
- SyncServer API
  - source of truth для мастер-данных каталога
  - принимает device/site headers

### Databases
- Local SQLite (Warehouse_web local data)
- External DB за SyncServer (catalog persistence)

## Data flow
```text
Browser
  → Warehouse_web URLs/Views
  → CatalogService
  → SyncServerClient (httpx)
  → SyncServer API
  → (external DB)
```

## Standalone vs distributed role
Проект не является полностью standalone для каталоговых операций: чтение и изменение `Category/Unit/Item` зависит от доступности SyncServer.
