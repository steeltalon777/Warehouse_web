# ADR-0001: Django as SyncServer Web Client

## Status
Accepted

## Context

The repository is a Django application that serves HTML pages, Django admin, and session-based web access. Warehouse domain data and business rules live in SyncServer.

## Decision

Treat Warehouse_web as a Django SSR web client for SyncServer, not as a second backend for warehouse logic.

## Consequences

Pros:
- keeps architectural ownership clear
- reduces duplicated business logic
- makes integration boundaries easier to document

Cons:
- runtime correctness depends on SyncServer availability
- some UI flows require remote orchestration instead of local CRUD

## Alternatives Considered

### Option 1
Let Django become a partial warehouse backend.

Why not chosen:
- would duplicate domain rules and data ownership

### Option 2
Expose only a SPA frontend and remove Django SSR.

Why not chosen:
- does not match the current repository structure and implemented admin/server-rendered flows
