# ADR-0002: SyncServer as Source of Truth

## Status
Accepted

## Context

The project needs clear ownership for sites, catalog master data, access scopes, balances, operations, and user sync state.

## Decision

SyncServer is the source of truth for warehouse domain data. Django stores only technical local state such as auth users, sessions, `SyncUserBinding`, and a transitional site mirror.

## Consequences

Pros:
- avoids split-brain domain ownership
- keeps domain validation centralized
- aligns local architecture with external API contracts

Cons:
- some local models remain as transitional tails and can be misleading
- admin and runtime flows must be designed around remote synchronization

## Alternatives Considered

### Option 1
Store catalog and site truth in Django too.

Why not chosen:
- would create inconsistent data ownership

### Option 2
Avoid all local persistence completely.

Why not chosen:
- Django still needs local auth/session state and user-token bindings
