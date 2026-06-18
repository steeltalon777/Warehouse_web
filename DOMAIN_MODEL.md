# DOMAIN_MODEL

`Warehouse_web` does not own warehouse domain entities. SyncServer owns catalog, operations, balances, users, sites, devices, access scopes, documents, recipients, and sync events.

## Local Technical State

## Django User

Purpose: web authentication and Django admin access.

Owner: Django.

## SyncUserBinding

Purpose: bind a Django user to a SyncServer user identity and token for server-side API calls.

Owner: Django technical integration layer.

## Site Mirror / Helper State

Purpose: web/admin convenience where still required by current flows.

Owner: Django technical integration layer.

## CatalogCacheItem

Purpose: local UX/search cache populated from SyncServer data.

Owner: Django cache layer, not domain truth.

## Remote Domain State

Remote state is accessed through `apps/sync_client/` wrappers and service classes. Domain validation and writes happen on SyncServer.
