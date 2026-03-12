# API_CONTRACT

## Internal Django routes
- `/users/*` — Django auth screens for technical admin/staff layer.
- `/admin/` — Django admin.
- `/client/*`, `/catalog/*` — SSR UI using service layer.

## External SyncServer contract (authoritative)
Warehouse domain reads/writes must go through SyncServer.

### Domain areas owned by SyncServer
- users
- roles
- sites
- catalog
- balances
- operations
- devices
- events

### Integration path in Warehouse_web
`Views -> CatalogService -> SyncServerClient -> SyncServer API`

### Required headers
- `X-Site-Id`
- `X-Device-Id`
- `X-Device-Token`
- `X-Client-Version`

## Contract guardrail
Django ORM models for legacy profile data are non-authoritative and transitional only.
