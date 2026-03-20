# Memory

## System Architecture

- Warehouse_web is a Django SSR web client for SyncServer.
- SyncServer is the warehouse domain owner.
- Django owns UI, sessions, Django admin, and a controlled integration layer.

## Core Entities

- local Django `User`
- `SyncUserBinding` for remote identity and per-user token storage
- local `Site` mirror used only as an admin convenience cache
- remote SyncServer entities: sites, scopes, categories, units, items, balances, operations, devices

## Data Model Decisions

- keep SyncServer as the source of truth for domain data
- keep local persistence minimal and technical
- keep user token storage separate from Django auth fields
- keep `UserProfile` only as a backward-compatibility tail during transition

## API Design

- all SyncServer traffic goes through `apps/sync_client`
- runtime client resolves headers from the current Django user context
- root admin flows use the root token
- per-user runtime flows use `SyncUserBinding.sync_user_token`
- Django admin drives root-managed user and site operations
- catalog browse pages use `/catalog/read/items` and `/catalog/read/categories`
- nomenclature management uses separate Django routes under `/nomenclature/`

## Business Rules

- Django must not implement warehouse business logic independently
- catalog master data is global for the whole organization
- read-only catalog is separate from nomenclature management
- nomenclature is a dedicated management section for chief/root
- `site_id` in catalog browse calls is only access context, not a real data partition
- final permission enforcement still happens in SyncServer

## Known Pitfalls

- local catalog ORM models still exist and can confuse new contributors; they are not the source of truth
- `UserProfile` still exists as deprecated compatibility state
- the local `Site` table is a mirror, not a domain owner
- runtime correctness still depends on testing against a real SyncServer

## Future Architecture

- finish migrating remaining catalog screens fully onto the current API-first model
- remove deprecated local domain tails when safe
- strengthen smoke tests around auth, token resolution, and SyncServer integration
