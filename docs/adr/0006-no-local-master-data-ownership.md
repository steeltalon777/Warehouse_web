# ADR-0006: No Local Master Data Ownership

## Status
Accepted

## Context

Categories, units, items, sites, and related access rules are owned by SyncServer. Local Django catalog models still exist as legacy tails from earlier stages.

## Decision

Do not treat local Django ORM models for warehouse master data as active sources of truth. Master data screens should be API-driven from SyncServer.

## Consequences

Pros:
- avoids local/remote divergence
- keeps Django focused on presentation and orchestration
- matches current API-first UI direction

Cons:
- transitional local models can still confuse contributors until fully removed
- some screens depend on remote availability even for read scenarios

## Alternatives Considered

### Option 1
Keep local ORM CRUD as a parallel source of truth.

Why not chosen:
- creates duplication and drift

### Option 2
Mirror all remote master data locally and read only from Django DB.

Why not chosen:
- not supported as the current architectural direction and would reintroduce backend ownership into Django
