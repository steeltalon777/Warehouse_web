# ADR-0003: Centralized SyncServer Client Layer

## Status
Accepted

## Context

Multiple feature areas need to call SyncServer APIs. Scattering raw HTTP calls through views and apps would make contracts inconsistent and increase coupling.

## Decision

Centralize SyncServer HTTP communication in `apps/sync_client`, with canonical runtime and root-admin clients plus endpoint-specific wrappers.

## Consequences

Pros:
- one place for headers, transport, and exception mapping
- easier contract updates
- thinner views and simpler testing seams

Cons:
- service and view layers must depend on the client layer instead of making quick direct calls
- legacy wrappers require cleanup during migration

## Alternatives Considered

### Option 1
Call `httpx` directly from each feature app.

Why not chosen:
- duplicates transport logic and error handling

### Option 2
Build separate client implementations per app.

Why not chosen:
- increases drift and reintroduces duplication
