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
- `GET /catalog/admin/categories`, `POST /catalog/admin/categories`, `GET /catalog/admin/categories/{id}`, `PATCH /catalog/admin/categories/{id}`, `DELETE /catalog/admin/categories/{id}`
- `GET /catalog/admin/units`, `POST /catalog/admin/units`, `GET /catalog/admin/units/{id}`, `PATCH /catalog/admin/units/{id}`, `DELETE /catalog/admin/units/{id}`
- `GET /catalog/admin/items`, `POST /catalog/admin/items`, `GET /catalog/admin/items/{id}`, `PATCH /catalog/admin/items/{id}`, `DELETE /catalog/admin/items/{id}`
- `GET /recipients`, `POST /recipients`, `GET /recipients/{id}`, `PATCH /recipients/{id}`, `DELETE /recipients/{id}`, `POST /recipients/merge`
- `GET /balances`
- `GET /operations`, `POST /operations`

## Required headers
`X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`.
