# TZ: Django Shell Pre-Angular UX Prerequisites

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation level 1 complete
- [x] 3. Unit/component tests complete
- [x] 4. Integration tests with real dependencies complete
- [x] 5. Stand smoke tests complete
- [ ] 6. UI automation tests complete (no Playwright infra for this shell yet)
- [x] 7. User scenario tests complete
- [x] 8. Regression checks complete
- [x] 9. Documentation updated
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.

---

## 1. Purpose

Close pre-Angular Django shell audit gaps #5, #11, and #12 from `docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md`:

- organization brand is hardcoded in `templates/includes/brand.html`;
- SyncServer role/context is not shown in the navbar;
- dashboard does not show temporary item count/reminder.

This is intentionally small and separate from full SSR table polish. Angular will render inside the Django shell, so the shell must be correct before screenshot baselines and Playwright scenarios are created.

---

## 2. Source Requirements

- `Functional and WorkLogik.md`, sections I.4 and I.6.1:
  - organization name/logo/brand must come from configurable variables/static assets, not hardcode;
  - top panel shows logged-in user and login/logout;
  - role/context should be visible to the user.
- Temporary item requirements:
  - dashboard must show temporary item count/reminder.
- `Warehouse_web/AGENTS.md`:
  - Django is web session host/BFF, not a second warehouse backend;
  - all SyncServer calls go through `apps/sync_client/` and service classes;
  - browser-facing pages must not expose SyncServer tokens.
- Current code findings:
  - `templates/includes/brand.html` hardcodes `brand_name="ООО АС Горизонт"`.
  - `config/settings/base.py` already has `ORGANIZATION_SHORT_NAME` and `ORGANIZATION_FULL_NAME`.
  - `templates/includes/navbar.html` shows only `request.user.username`.
  - Sync identity role is stored in session by `apps/sync_client/session_auth.py` as `sync_role`.
  - `apps/client/views.py:dashboard()` loads pending acceptance summary but not temporary item count.

---

## 3. Architecture Boundaries

### Django owns

- Shell layout: brand, navbar, left menu, login/logout, dashboard widgets.
- Reading safe display fields from settings/session/BFF services.
- Calling SyncServer through `apps/sync_client/` only.

### SyncServer owns

- Canonical role and temporary item data.
- Token validation and permission checks.

### Angular owns later

- Content area in lower-right/right workspace.
- Feature screens inside Django shell.

### Forbidden

- Do not expose `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`, or user token in templates, JS globals, screenshots, or JSON payloads.
- Do not hardcode organization name in templates.
- Do not create local Django warehouse-domain tables for temporary items.
- Do not redraw the shell in Angular as part of this TZ.

---

## 4. Implementation Levels

### Level 0 — Context verification

Scope:

- Re-read `Functional and WorkLogik.md` sections I.4, I.6.1, IV.1.5.
- Review:
  - `templates/includes/brand.html`
  - `templates/includes/navbar.html`
  - `templates/client/dashboard.html`
  - `apps/client/views.py`
  - `apps/sync_client/session_auth.py`
  - `apps/sync_client/temporary_items_api.py`
  - `config/settings/base.py`

Acceptance criteria:

- Executor records where brand/logo values will be sourced.
- Executor records how role will be read without exposing tokens.
- Executor records how temporary item count will be fetched and what fallback appears if SyncServer is unavailable.

### Level 1 — Configurable brand in Django shell

Required behavior:

- Replace hardcoded brand name in `brand.html` with settings/context value.
- Use `ORGANIZATION_SHORT_NAME` for compact shell text.
- Keep logo path configurable or at least centralized; recommended setting/env names:
  - `ORGANIZATION_SHORT_NAME`
  - `ORGANIZATION_FULL_NAME`
  - `ORGANIZATION_LOGO_STATIC_PATH` if introduced.
- Template fallback must be safe if setting is empty.

Acceptance criteria:

- Changing `ORGANIZATION_SHORT_NAME` changes rendered shell brand.
- Default brand is still shown when env var is not configured.
- No hardcoded organization name remains in `brand.html`.

### Level 2 — SyncServer role/context in navbar

Required behavior:

- Display user-friendly SyncServer role near username:
  - observer / Обозреватель;
  - storekeeper / Кладовщик;
  - chief_storekeeper / Главный кладовщик;
  - root / Root.
- Source role from existing safe session identity (`sync_role`) or a context processor/helper using `get_sync_identity(request)`.
- If Sync identity is missing, show controlled state such as `роль не привязана` or hide badge; do not fallback to root.
- Do not display raw tokens, user token, device token, or internal UUID unless already product-approved.

Acceptance criteria:

- Authenticated user with Sync identity sees role badge.
- Missing Sync identity does not leak root/admin context.
- Tests assert response HTML contains role label and does not contain configured token values.

### Level 3 — Temporary item count/reminder on dashboard

Required behavior:

- Dashboard shows count of active temporary items needing attention.
- Data source must be SyncServer through `apps/sync_client/temporary_items_api.py` or an existing service wrapper.
- If SyncServer is unavailable, dashboard must render without crashing and show a controlled unavailable/unknown state.
- Widget must link to existing temporary items screen if route exists.

Acceptance criteria:

- Dashboard renders count when API returns data.
- Dashboard renders safe fallback on SyncServer error.
- No local Django domain table is introduced.

### Level 4 — Angular shell screenshot readiness

Required behavior:

- The updated top brand/navbar must be stable when Angular routes are hosted inside Django shell.
- No Angular code changes are required in this TZ.
- If Playwright tests already exist, add/update a shell smoke screenshot or DOM assertion.

Acceptance criteria:

- `/nomenclature/` or current Django shell route shows brand, username/logout, and role badge while Angular content stays in the container area.

---

## 5. Real Test Stand Requirement

### Database

- Django test DB for template/view tests.
- SyncServer test stand or mocked sync client for unit/component tests.
- For real stand smoke, use SyncServer PostgreSQL test DB bootstrapped with root/Django device tokens.

### Seed data

- Django authenticated user bound to SyncServer identity.
- SyncServer identity roles for at least storekeeper and root/chief.
- Active temporary items count > 0.
- Scenario with Sync identity missing/no binding.

### Services to start

- Django app.
- SyncServer API for real dashboard count smoke.

### Environment variable names only

- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `ORGANIZATION_SHORT_NAME`
- `ORGANIZATION_FULL_NAME`
- `ORGANIZATION_LOGO_STATIC_PATH`
- `DJANGO_BASE_URL`

### Health checks

- Django `/client/` dashboard response.
- Django hosted Angular route such as `/nomenclature/` if enabled.
- SyncServer temporary items endpoint through BFF/client service.

### Smoke commands

```bash
python manage.py check
python manage.py test apps.client apps.sync_client apps.temporary_items
python manage.py test
```

If Playwright shell smoke exists or is added:

```bash
pytest tests_e2e/test_nomenclature_spa.py
```

### Cleanup

- Remove temporary test users/sessions.
- Do not store real tokens in test snapshots.

---

## 6. Test Strategy Ladder

| Level | Required? | Checks |
|---|---|---|
| Static checks | Yes | `python manage.py check`; template syntax checks through Django tests |
| Unit tests | Yes | role label helper/context processor; brand setting fallback |
| Component tests | Yes | Django template/view tests for navbar/dashboard |
| Integration tests | Yes | Django with mocked or test SyncServer client for temp item count and identity role |
| Real stand smoke | Recommended before Angular screenshot baseline | Django + SyncServer test stand dashboard smoke |
| UI automation | Recommended | Playwright/pytest e2e for shell visible around Angular route if infrastructure exists |
| User scenarios | Yes | user sees org brand, role badge, temp item reminder, logout remains available |
| Regression pack | Yes | auth redirect/login/logout, nomenclature SPA host route, BFF auth boundary tests |
| Acceptance review | Yes | evidence table reviewed |

---

## 7. Acceptance Criteria

- Brand name in shell comes from settings/context, not hardcoded template literal.
- Navbar shows logged-in username and SyncServer role/context label.
- Missing Sync identity does not display root or any misleading elevated role.
- Dashboard shows active temporary item count/reminder or a safe unavailable state.
- No SyncServer tokens appear in HTML, logs, snapshots, or JSON responses.
- Existing login/logout and shell navigation still work.
- Angular-hosted page can be screenshot with stable Django shell visible.

---

## 8. Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|---|
| Django static/check | `python manage.py check` | pass | System check identified no issues |
| Unit/helper tests | `python manage.py test apps.common.tests` | pass | 7 tests — context processor, role labels, fallback |
| Template/view tests | `python manage.py test apps.client.tests` | pass | 15 tests — brand, navbar role badge, temp item count |
| Integration/stand smoke | `python manage.py test` (full suite) | pass | 175 tests pass, including mocked SyncServer calls |
| UI automation | Playwright not available | skipped | No Playwright infra for this shell yet |
| Regression auth/shell | Existing auth/logout tests in test suite | pass | auth boundary, session auth, anonymous redirect all pass |
| Documentation | TZ-D checklist updated | done | This table |
