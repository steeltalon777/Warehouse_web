# Warehouse_web Agent Contract

## Role

`Warehouse_web` is the active Django web client, session host, admin UI, and BFF layer for browser features.

## Functional Requirements Authority

- `Functional and WorkLogik.md` at the workspace root is the **canonical functional requirements document** for operation types, user roles, workflows, and UI behaviour rules.
- Before implementing any BFF endpoint, Django view, or UI flow, re-read the relevant section of `Functional and WorkLogik.md` and confirm alignment.
- If a BFF endpoint exposes a subset of a domain feature (e.g., operations without certain types), document the scope decision explicitly.

## Rules

- Django is not a second warehouse backend.
- SyncServer owns catalog, operations, balances, users, sites, devices, and business rules.
- All SyncServer calls go through `apps/sync_client/` and service classes.
- Do not add local Django ORM models for warehouse catalog/domain entities.
- Local Django storage is allowed only for technical web state: auth, sessions, bindings, cache, and UI/BFF support.
- Browser-facing JSON APIs must not expose SyncServer tokens.
- Angular integration must use Django auth, CSRF, and same-origin BFF endpoints.
- Frontend SPA architecture is governed by `../Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`.
- Django shell is permanent: topbar, brand/user/logout/admin controls, left navigation, session, CSRF, and authenticated layout stay in Django.
- Business URLs should open Angular screens once migrated; replaced Django SSR screens must move under explicit `/ssr/` fallback routes.
- Do not mount unrelated Angular screens under another feature prefix as a final route, for example `/nomenclature/operations/` must not be the final operations route.
- When changing sidebar links for migrated screens, link to the business URL that renders Angular inside the Django content area.

## Git Rules

- Agents may commit completed Django/BFF changes after relevant checks/tests pass.
- Commit only from the `dev` branch.
- Switching from `dev` to another branch is forbidden by default.
- If the branch is not `dev`, warn the user and do not commit until the user gives an explicit command.
- If checks/tests fail, are unavailable, or were not run, do not commit and ask the user what to do.
- Git push is completely forbidden; the user pushes manually.

## Current Priority

The main active feature direction is the Django-hosted Angular content application: Django shell remains permanent, Angular screens mount inside the content area, and browser data access goes through Django BFF endpoints.

## Verification

- Run `python manage.py test` after changes.
- When changing `apps/sync_client/`, verify affected Django views or BFF endpoints as well.
