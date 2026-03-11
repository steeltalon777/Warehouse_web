# AI_CONTEXT

## Non-negotiable rules
- **Warehouse_web is NOT source of truth for warehouse catalog.**
- Business master-data (`Category`, `Unit`, `Item`) is stored and controlled in SyncServer.
- Warehouse_web must interact with catalog through SyncServer HTTP API.
- Local Django DB is only for Django-specific concerns (users, auth, sessions, admin).

## Coding guidance
- Keep catalog business logic in service/integration layers.
- Views should orchestrate request/response and permission checks.
- Handle SyncServer errors explicitly: 400, 404, 409, 5xx.

## Integration headers
Every SyncServer request includes:
- `X-Site-Id`
- `X-Device-Id`
- `X-Device-Token`
- `X-Client-Version`
