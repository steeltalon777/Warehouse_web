# MEMORY

## Architectural memory
- Django is not warehouse domain source of truth.
- SyncServer is the single domain authority.
- Django auth is technical admin/staff/root layer only.

## Current transition state
- Legacy `UserProfile/Site/Role` remains in codebase for compatibility.
- Legacy profiles are optional and deprecated.
- Django superuser must work without `users_userprofile` table dependency.

## Integration memory
- Keep API-first integration through `apps/integration/syncserver_client.py` and service layer.
- Do not move domain users/roles/sites/catalog into Django ORM ownership.

## Deployment memory
- Production Django DB must be PostgreSQL (env-configured).
- Do not use sqlite in production.
- In docker network, SyncServer URL should be `http://syncserver:8000`.
