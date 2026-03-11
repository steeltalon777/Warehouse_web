# API_CONTRACT

## Internal HTTP API (Django routes)

### Root routes (`config/urls.py`)
- `GET /admin/`
- `GET|POST /catalog/...`
- `GET /client/`
- `GET|POST /users/...`
- `GET /documents/...` (namespace exists, no endpoints)

### Catalog routes (`apps/catalog/urls.py`)
- `GET /catalog/` — catalog home
- `GET /catalog/categories/` — categories list
- `GET|POST /catalog/categories/create/` — create category
- `GET|POST /catalog/categories/<uuid:pk>/edit/` — update category
- `GET|POST /catalog/categories/<uuid:pk>/deactivate/` — deactivate category (`is_active=false`)
- `GET /catalog/categories/tree/` — category tree
- `GET /catalog/units/` — units list
- `GET|POST /catalog/units/create/` — create unit
- `GET|POST /catalog/units/<uuid:pk>/edit/` — update unit
- `GET /catalog/items/` — items list (`category_id`, `search` query params)
- `GET|POST /catalog/items/create/` — create item
- `GET|POST /catalog/items/<uuid:pk>/edit/` — update item
- `POST /catalog/items/<uuid:pk>/deactivate/` — deactivate item (`is_active=false`)

### Auth routes (`apps/users/urls.py`)
- `GET|POST /users/login/`
- `POST /users/logout/`

### Client routes (`apps/client/urls.py`)
- `GET /client/` — dashboard

## External API contract (SyncServer)
OpenAPI/Swagger specification в этом репозитории отсутствует.
Фактический контракт зафиксирован в `SyncServerClient`.

### Read endpoints
- `GET /catalog/categories`
- `GET /catalog/categories/tree`
- `GET /catalog/units`
- `GET /catalog/items?category_id=&search=`

### Write endpoints
- `POST /catalog/admin/categories`
- `PATCH /catalog/admin/categories/{category_id}`
- `POST /catalog/admin/units`
- `PATCH /catalog/admin/units/{unit_id}`
- `POST /catalog/admin/items`
- `PATCH /catalog/admin/items/{item_id}`

### Required headers for SyncServer
- `X-Site-Id`
- `X-Device-Id`
- `X-Device-Token`
- `X-Client-Version`

### Error handling contract
- `400`: validation/business input errors
- `404`: entity not found
- `409`: conflict/duplicates/invalid relation
- `5xx`: server unavailable path in UI
