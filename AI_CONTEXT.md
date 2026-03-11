# AI_CONTEXT

## System architecture
- Application type: Django SSR client.
- Role: warehouse web UI and access control.
- External dependency: SyncServer for catalog master data.

## Backend rules
- Keep catalog business flow through `CatalogService`.
- Do not call low-level SyncServer client directly from templates/forms.
- Convert integration failures to deterministic user-facing outcomes.

## Database rules
- Local DB stores Django/auth/application-local records.
- SyncServer DB remains source of truth for catalog entities.
- Do not introduce direct writes from Warehouse_web to SyncServer PostgreSQL.

## Layered architecture
- API: Django URLs + views
- Services: orchestration and error mapping
- Repositories/Data: integration client + local ORM
- Models: catalog + users/access models

## Client rules
- UI is server-rendered via Django templates.
- Protected pages require login and role checks.

## Architecture constraints
- Required Sync headers: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`.
- SyncServer timeout must be bounded.
- Warehouse_web must preserve client-only responsibility in multi-repo system.
