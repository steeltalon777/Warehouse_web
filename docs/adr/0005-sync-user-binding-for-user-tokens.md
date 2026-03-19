# ADR-0005: SyncUserBinding for Per-User Tokens

## Status
Accepted

## Context

Non-root runtime requests to SyncServer require per-user tokens. Root requests use a root token from environment variables. This token data should not be mixed into Django auth fields.

## Decision

Store SyncServer user identity and token state in a dedicated `SyncUserBinding` model linked one-to-one with the Django user.

## Consequences

Pros:
- separates local auth identity from remote sync identity
- supports sync status, repair flows, token rotation, and admin recovery
- keeps token handling explicit

Cons:
- adds one more model to maintain
- transitional compatibility code still exists around legacy profile data

## Alternatives Considered

### Option 1
Store SyncServer token fields directly on Django user.

Why not chosen:
- mixes local auth concerns with remote integration state

### Option 2
Store all user tokens only in session.

Why not chosen:
- does not support durable admin sync, repair, or token rotation workflows
