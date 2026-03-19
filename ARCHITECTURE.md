# Architecture

## System Overview

Warehouse_web is a Django SSR application that acts as a web client for SyncServer. SyncServer owns warehouse domain data and business rules. Django provides screens, forms, admin tooling, session handling, and a controlled integration layer.

## High-Level Architecture

```text
Clients
  Browser
    ->
API / Application Layer
  Django views, forms, admin actions
    ->
Service Layer
  app services orchestrating UI flows
    ->
Repository / Data Layer
  apps/sync_client HTTP clients and API wrappers
    ->
Database / External System
  SyncServer database and APIs
```

Local Django persistence exists only for technical state such as auth users, sessions, `SyncUserBinding`, and a temporary site mirror.

## Application Layers

### API Layer

- Django URL routing in `config/urls.py`
- SSR views in `apps/catalog`, `apps/client`, `apps/operations`, `apps/balances`, `apps/admin_panel`
- Django admin in `apps/users/admin.py`

This layer handles requests, validates forms, selects UI flows, and delegates integration work.

### Service Layer

- `apps/users/services.py`
- `apps/catalog/services.py`
- `apps/client/services.py`

This layer orchestrates multi-step flows such as user sync, site sync, catalog CRUD, and domain page preparation.

### Repository / Data Layer

- `apps/sync_client/client.py`
- `apps/sync_client/root_admin_client.py`
- `apps/sync_client/catalog_api.py`
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`
- `apps/sync_client/access_api.py`
- `apps/sync_client/admin_api.py`

This layer owns HTTP transport, headers, exception mapping, and endpoint-specific wrappers.

### Models / Entities

Local Django models are intentionally narrow:

- `auth.User`
- `SyncUserBinding`
- `Site`
- `UserProfile` as a deprecated compatibility tail

Legacy local catalog models still exist in the repo, but they are not the source of truth.

## Data Model

### Core Local Entities

- `User`
  - Django authentication identity for the web client
- `SyncUserBinding`
  - links a Django user to `syncserver_user_id`
  - stores `sync_user_token`
  - tracks sync role, default site, assigned site ids, sync status, and last sync metadata
- `Site`
  - local mirror of SyncServer sites
  - used only for Django-admin convenience during transition

### Remote Domain Entities in SyncServer

- sites
- user access scopes
- categories
- units
- items
- balances
- operations
- devices and access records

## Data Flow

Example runtime request:

```text
Browser
  -> Django view
  -> App service
  -> SyncServerClient
  -> SyncServer API
  -> SyncServer database
  -> response mapped back to Django template
```

Example root admin user-management flow:

```text
Django admin form
  -> UserSyncService
  -> SyncServerRootAdminClient
  -> POST /auth/sync-user
  -> PUT /admin/users/{user_id}/scopes
  -> local SyncUserBinding update
```

## Architectural Principles

- SyncServer is the source of truth for warehouse domain state.
- Django must not become a second backend for catalog, sites, balances, or operations.
- Views should stay thin and should not issue raw HTTP requests directly.
- SyncServer communication must stay centralized in `apps/sync_client`.
- Root-managed users and sites are administered through Django admin.
- Non-root runtime calls use per-user tokens from `SyncUserBinding`.
- Local mirrors and compatibility models must not drive domain truth.

## External Integrations

- SyncServer HTTP API
- relational database configured for Django itself
- Docker / Gunicorn deployment stack

## Future Architecture

- remove legacy local catalog ORM tail once all screens are fully API-driven
- finish migration away from deprecated `UserProfile`
- further reduce transitional site mirror behavior if remote-backed admin screens become sufficient
- add stronger runtime validation and smoke-test coverage against a real SyncServer
