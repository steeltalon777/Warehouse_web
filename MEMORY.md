# MEMORY

## System architecture
- Django modular monolith with SSR templates
- Layered request path: URL/View -> Service -> Integration client
- SyncServer is external backend authority for catalog master data

## Core entities
- Catalog: `Category`, `Unit`, `Item`
- Access control: `UserProfile` with `Role`, optional `Site`

## Data model decisions
- UUID primary keys for catalog entities
- Category supports tree hierarchy (`parent` self-reference)
- User profile extends Django user by OneToOne relation
- Catalog entities are represented in Django domain model, but operational truth is maintained in SyncServer

## API design
- Internal interface: Django routes for SSR pages (`/catalog`, `/client`, `/users`)
- External integration interface: centralized SyncServer HTTP client
- Service layer maps transport/API failures to deterministic UI errors

## Business rules
- Catalog management is restricted to elevated roles (`root`, `chief_storekeeper`)
- Dashboard requires authenticated active user profile (or superuser)
- Catalog create/update/deactivate actions are executed through SyncServer admin endpoints

## Known pitfalls
- Catalog pages depend on SyncServer availability
- Missing sync headers/credentials break external API calls
- Documents module exists as scaffold and is not yet a full domain feature

## Future architecture
- Grow `apps/documents` using current layering rules
- Extend observability and resilience around external SyncServer dependency
- Keep architectural decisions synchronized with ADRs in `docs/adr/`
