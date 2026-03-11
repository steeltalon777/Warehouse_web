# MEMORY

## System architecture
- Django 6 modular monolith with SSR templates.
- Routing in `config/urls.py`, feature apps in `apps/*`.
- Catalog operations flow through service + integration layers.

## Core entities
- `Category`, `Unit`, `Item` (catalog domain).
- `Site`, `UserProfile`, `Role` (user access domain).

## Data model decisions
- UUID PK for catalog entities.
- Hierarchical categories via self-FK (`parent`).
- `Item.unit` protected on delete; `Item.category` nullable.
- User profile is separate model linked OneToOne to Django User.

## API design
- Internal API is server-rendered Django endpoints (`/catalog/*`, `/client/*`, `/users/*`).
- External dependency: SyncServer HTTP API via `SyncServerClient`.
- SyncServer calls always include site/device/client headers.

## Business rules
- Catalog management allowed for root/chief_storekeeper.
- Client dashboard доступен активным пользователям с профилем (или superuser).
- Ошибки SyncServer маппятся в user-facing сообщения через `ServiceResult`.

## Known pitfalls
- `apps/documents` пока пустой (нет бизнес-логики/endpoint-ов).
- Runtime-зависимость от SyncServer: при недоступности внешнего API каталоговые страницы деградируют в ошибки.
- В репозитории есть локальные catalog models, но operational truth находится во внешнем сервисе.

## Future architecture
- Развитие документов и складских операций через ту же layered схему.
- Возможное добавление read-cache при сохранении SyncServer как source of truth.
