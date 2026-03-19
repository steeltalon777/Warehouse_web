# AI Context

## System Architecture

Warehouse_web is a Django SSR client for SyncServer. It is not a second backend. SyncServer owns warehouse domain data, access scopes, and business rules.

## Backend Rules

- keep business logic in SyncServer whenever possible
- keep Django views thin
- put multi-step orchestration into service classes
- route every new SyncServer HTTP call through `apps/sync_client`
- do not add raw `httpx` calls directly inside views or templates

## Database Rules

- local Django DB is for technical application state
- local truth includes auth users, sessions, `SyncUserBinding`, and a transitional site mirror
- local catalog tables are legacy-only and must not become active domain storage again
- do not treat local `Site` as the source of truth

## Layered Architecture

### API

- Django URLs, SSR views, Django admin actions

### Services

- user sync, site sync, catalog orchestration, domain page preparation

### Repositories

- SyncServer HTTP clients and endpoint wrappers in `apps/sync_client`

### Models

- `User`
- `SyncUserBinding`
- `Site`
- `UserProfile` only as compatibility tail

## Client Rules

- root admin operations use the root token from environment variables
- non-root runtime operations use per-user tokens from `SyncUserBinding`
- runtime headers are resolved by the canonical SyncServer client layer
- Django admin is the canonical UI for root-managed users and sites

## Architecture Constraints

- do not redesign SyncServer contracts from Django
- do not move warehouse business rules into Django models
- do not create a second catalog/site source of truth in Django
- treat `site_id` as access context for global catalog master data unless SyncServer behavior changes
- prefer deleting deprecated paths over keeping parallel active flows
