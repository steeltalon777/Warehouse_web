# ADR-0004: Django Admin for Root Management

## Status
Accepted

## Context

Root-managed workflows such as user creation, site management, scope assignment, sync, and token rotation need a single operational UI in Django.

## Decision

Use Django admin as the canonical UI for root-managed users and sites. Do not keep parallel active user or site CRUD flows in the main application UI.

## Consequences

Pros:
- one operational surface for privileged actions
- clearer separation between worker UI and admin UI
- simpler navigation and fewer duplicate flows

Cons:
- admin customization becomes part of the main integration layer
- recovery and synchronization tools must be exposed through admin workflows

## Alternatives Considered

### Option 1
Keep root management in custom front-office pages.

Why not chosen:
- duplicates admin concerns and spreads privileged logic across multiple UIs

### Option 2
Manage users and sites only manually outside Django.

Why not chosen:
- would remove required operational workflows from the application
