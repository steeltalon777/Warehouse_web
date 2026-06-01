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

- Parallel sessions are normal. `git status` may show unrelated modified/untracked files from other agents or the user; this is not a blocker by itself.
- Commit only from the `dev` branch.
- Switching from `dev` to another branch is forbidden by default.
- If the branch is not `dev`, warn the user and do not commit until the user gives an explicit command.
- Agents MUST commit their own completed Django/BFF changes after relevant checks/tests pass.
- Stage and commit only files intentionally changed for the assigned task, using explicit pathspecs such as `git add -- path/to/file`. Do not use broad `git add .` or `git add -A` for task commits.
- Git does not auto-track new files by itself; untracked files become tracked only after staging. Keep local/service artifacts ignored and unstaged unless explicitly assigned.
- Before committing, inspect the staged diff and confirm it contains only task-owned files. Leave unrelated dirty files unstaged.
- If intended edits overlap with unrelated changes in the same file, stop and ask the user/orchestrator how to split ownership before committing.
- If checks/tests fail, are unavailable, or were not run, do not commit unless the user explicitly instructs to commit with that limitation documented.
- Git push is completely forbidden; the user pushes manually.

## Current Priority

The main active feature direction is the Django-hosted Angular content application: Django shell remains permanent, Angular screens mount inside the content area, and browser data access goes through Django BFF endpoints.

## Transport & SyncServer Integration

- All raw HTTP calls to SyncServer use the persistent transport in `apps/sync_client/transport.py`.
- `get_sync_client()` returns a process-global `httpx.Client` with connection pooling. Do not create `httpx.Client()` directly.
- `execute_with_retry()` provides automatic retry for idempotent GET/HEAD/OPTIONS requests.
- Per-request auth headers (X-User-Token, X-Device-Token) are still resolved per-request in `SyncServerClient.build_headers()`.
- X-Request-Id is automatically forwarded from Django to SyncServer when the `RequestTracingMiddleware` is active.
- Error mapping is centralized in `client.py` (`_raise_for_response`) and `root_admin_client.py`.
- Timeouts are configured per-setting: `SYNC_SERVER_CONNECT_/READ_/WRITE_/POOL_TIMEOUT`.
- Cache policy: Django `CACHES` configured for BFF acceleration. Do not cache tokens or write decisions.
  See `config/settings/base.py` for allowed/forbidden cache data.

## Dev-стенд и тестирование

Агенты тестируют изменения на работающем dev-стенде. По умолчанию стенд запущен. Если нет — агент может запустить/перезапустить/пересобрать его через `make` из `/home/makc/AI_sandbox/warehouse_solution`.

- Полный список `make`-команд и протокол восстановления стенда: `AGENTS.md` в корне workspace.
- Основные команды: `make up` (запуск), `make restart` (перезапуск), `make build-web` (ребилд Warehouse_web), `make status` (проверка).

## Verification

- Run `python manage.py test` after changes.
- When changing `apps/sync_client/`, verify affected Django views or BFF endpoints as well.
- After transport changes, run `apps.sync_client.tests` and `apps.sync_client.test_auth_boundary`.
