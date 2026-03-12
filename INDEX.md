# INDEX

## Core docs
- `README.md` — high-level architecture and setup
- `SYSTEM_MAP.md` — component map and ownership boundaries
- `AI_CONTEXT.md` — AI-safe architecture constraints
- `AI_ENTRY_POINTS.md` — critical code entrypoints
- `API_CONTRACT.md` — internal/external contract boundaries
- `MEMORY.md` — persistent architectural memory
- `PROJECT_BRAIN.md` — roadmap intent
- `DEPLOYMENT.md` — deployment and env policy

## Critical architecture statement
- Django is a web/admin client and technical auth layer.
- SyncServer is the source of truth for warehouse domain.
- Production Django DB must be PostgreSQL service DB (not sqlite).
- Legacy `apps/users` profile models are deprecated transition layer.
