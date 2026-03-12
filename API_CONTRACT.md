# API_CONTRACT

## Django internal routes
- `/users/login`, `/users/logout` — technical auth.
- `/client/root/users/*` — root/admin control panel.
- `/catalog/*` — chief catalog interface.
- `/client/catalog`, `/client/balances`, `/client/operations*` — storekeeper/chief work UI.

## SyncServer authoritative areas
- users
- roles
- sites
- catalog
- balances
- operations
- devices
- events

## Sync endpoints used by Warehouse_web
- `GET /users`, `POST /users`, `PATCH /users/{id}`
- `GET /roles`, `GET /sites`
- `POST /catalog/categories`, `GET /catalog/categories/tree`
- `POST /catalog/units`, `POST /catalog/items`
- `POST /catalog/admin/categories`, `PATCH /catalog/admin/categories/{id}`
- `POST /catalog/admin/units`, `PATCH /catalog/admin/units/{id}`
- `POST /catalog/admin/items`, `PATCH /catalog/admin/items/{id}`
- `GET /balances`
- `GET /operations`, `POST /operations`

## Required headers
`X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`.
