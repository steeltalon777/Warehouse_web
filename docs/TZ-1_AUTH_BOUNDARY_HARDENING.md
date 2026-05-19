# TZ-1: Auth boundary hardening for Warehouse_web BFF

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Auth policy decision documented
- [x] 3. Canonical token resolution implemented
- [x] 4. Root-token fallback removed from normal user flows
- [x] 5. `SYNC_DEVICE_TOKEN` policy resolved and implemented
- [x] 6. `simple_client.py` removed from active auth flows or isolated as legacy-only
- [x] 7. Unit/component tests complete
- [ ] 8. Django integration tests complete
- [ ] 9. Stand smoke tests complete
- [ ] 10. Regression checks complete
- [ ] 11. Documentation updated
- [ ] 12. Final acceptance review complete

## Check Rules

- Architect owns this checklist, scope, boundaries, and acceptance criteria.
- Executor agents may check implementation/test items only after implementing the item and attaching verification evidence.
- QA verifier may check final acceptance only after reviewing command output, test coverage, and blocker notes.
- If a real SyncServer stand is unavailable, stand smoke remains unchecked and the blocker is documented.
- No checkbox may be checked solely because mocked tests passed when the level requires Django integration or stand evidence.

---

## 0. Purpose

Harden the `Warehouse_web` BFF authentication boundary so a normal Django user can never be silently escalated to SyncServer root privileges.

The target outcome:

- One canonical SyncServer client path for active Django/BFF flows.
- No fallback from a regular Django user to `SYNC_ROOT_USER_TOKEN`.
- Root token use is explicit, auditable, and limited to approved admin/system flows.
- `SYNC_DEVICE_TOKEN` behavior is documented and no longer contradicts SyncServer auth rules.
- Legacy `simple_client.py` is removed from active auth paths or isolated so it cannot bypass the canonical policy.

---

## 1. Current Findings From Review

### 1.1 Root fallback in canonical client

File: `apps/sync_client/client.py`

Current behavior:

- `SyncServerClient.__init__` loads both `SYNC_DEVICE_TOKEN` and `SYNC_ROOT_USER_TOKEN`.
- `_resolve_user_token()` returns root token when `force_root=True`.
- `_resolve_user_token()` also returns root token for any authenticated Django superuser.
- If a non-root user has no binding/session token, it logs a warning and returns root token.

Observed risky block:

```python
logger.warning(
    "Sync user token not in binding/session for Django user '%s', falling back to root token",
    request_user.username,
)
return self.root_user_token
```

This is the primary privilege escalation bug.

### 1.2 Session auth root fallback

File: `apps/sync_client/session_auth.py`

Current behavior:

- `_resolve_sync_user_token()` pulls token from response/session.
- If request user is superuser, it falls back to `SYNC_ROOT_USER_TOKEN`.
- For non-superuser, it tries `request_user.sync_binding.sync_user_token`.

This may be acceptable only if the superuser flow is explicitly classified as an admin/root flow. It must not be an implicit fallback for normal BFF calls.

### 1.3 Legacy `simple_client.py` is still in active auth path

Files:

- `apps/sync_client/simple_client.py`
- `apps/sync_client/auth_api.py`

Current behavior:

- `auth_api.py` imports `SyncClient` from `.simple_client`.
- `simple_client.py` constructs headers independently from the canonical `SyncServerClient`.
- It has its own token lookup order: session token -> legacy `user_token` -> superuser root token -> binding token.

Even if `SyncServerClient` is fixed, `AuthAPI` can still bypass policy through the legacy client.

### 1.4 `SYNC_DEVICE_TOKEN` contradiction

Files:

- `apps/sync_client/client.py`
- `apps/sync_client/root_admin_client.py`
- `apps/sync_client/simple_client.py`
- `config/settings/base.py`

Current behavior:

- `SyncServerClient` raises `RuntimeError` if `SYNC_DEVICE_TOKEN` is not configured.
- It sends `X-Device-Token` on all calls.
- `SyncServerRootAdminClient` also requires and sends `X-Device-Token`.

But `API_MAP.md` says primary user/business APIs use `X-User-Token`; `X-Device-Token` is used by `/ping`, `/push`, `/pull`, and compatibility catalog POST routes.

This TZ requires an explicit policy decision:

- Preferred target: for `Warehouse_web` BFF user-token calls, `SYNC_DEVICE_TOKEN` is optional audit context only; absence must not break normal `/auth`, `/catalog`, `/operations`, `/balances`, `/documents`, `/recipients`, `/temporary-items`, `/reports`, and admin user-token calls.
- If maintainers decide to keep it required for audit, that requirement must be documented and enforced consistently without implying it grants permissions.

### 1.5 Existing root usages that must be classified

Known call sites:

| File | Current root use | Required action |
|---|---|---|
| `apps/operations/services.py` | `SyncServerClient(request=self.request, force_root=True)` in `get_all_sites()` | Classify as admin/system or replace with accessible-site lookup |
| `apps/catalog_cache/services.py` | `SyncServerClient(force_root=True)` | Keep only if this is system cache/admin job; otherwise restrict |
| `apps/balances/views.py` | root client in `_get_sites_index()` | Must not use root for normal user page decoration unless explicitly authorized |
| `apps/common/views.py` | health check uses `force_root=True` | Prefer unauthenticated `/health`/`/ready`; or restrict to staff/system |
| `apps/sync_client/root_admin_client.py` | dedicated root admin client | Keep only for staff/superuser admin flows |

---

## 2. Architecture Boundaries

### 2.1 Canonical client rule

All active Warehouse_web -> SyncServer calls must use one canonical auth policy.

Allowed active transport:

- `apps.sync_client.client.SyncServerClient` for user/session-bound BFF calls.
- `apps.sync_client.root_admin_client.SyncServerRootAdminClient` only for explicit Django staff/superuser admin flows or system/admin jobs.

Forbidden active transport:

- `apps.sync_client.simple_client.SyncClient` for new or active auth/business/BFF flows.

### 2.2 Token ownership

| Token | Allowed owner/use |
|---|---|
| `sync_binding.sync_user_token` | Normal Django user -> SyncServer user identity |
| Session `sync_user_token` | Short-lived session copy of bound SyncServer identity |
| `SYNC_ROOT_USER_TOKEN` | Explicit root/admin/system flows only |
| `SYNC_DEVICE_TOKEN` | Device-sync endpoints or optional audit context depending on Level 0 decision |

### 2.3 Root token rule

`SYNC_ROOT_USER_TOKEN` may be used only when at least one condition is true:

1. The caller explicitly passes `force_root=True` and the call site is documented as admin/system.
2. The call is handled by `SyncServerRootAdminClient` from a Django staff/superuser admin flow.
3. The call is a health/system/cache job explicitly listed in the root-use allowlist.

Normal user-facing BFF/view/service calls must never obtain root token because a binding/session token is missing.

### 2.4 Missing binding rule

If an authenticated non-superuser has no SyncServer binding/session token:

- Do not fallback to root.
- Raise a controlled auth error (`SyncAuthError`, `SyncForbiddenError`, or a new explicit `SyncIdentityNotBoundError`).
- Views/BFF endpoints must convert that error into 401/403 or a controlled user-facing error.

---

## 3. Level 0 — Policy Decision and Root-Use Inventory

### 3.1 Scope

Before implementation, freeze the policy so all code changes point in one direction.

### 3.2 Deliverables

1. Add a short policy document, one of:
   - `docs/syncserver_auth_boundary.md`, or
   - update `docs/syncserver_auth_integration.md` / `docs/syncserver_session_auth_integration.md`.
2. Create a root-use inventory table with every `force_root=True`, `SYNC_ROOT_USER_TOKEN`, and `SyncServerRootAdminClient` use.
3. Classify each root use as:
   - `admin_staff_flow`;
   - `system_health_or_cache`;
   - `must_remove`;
   - `needs_product_decision`.
4. Decide `SYNC_DEVICE_TOKEN` policy:
   - `optional_audit_context_for_web_business_calls`, preferred; or
   - `required_audit_context_for_all_web_calls`, if explicitly accepted.

### 3.3 Acceptance

- No implementation starts before every known root call site is classified.
- The chosen `SYNC_DEVICE_TOKEN` policy is documented.
- The policy states that no missing regular-user binding can fallback to root.

### 3.4 Verification

- Documentation review by architect/docs-curator.
- Grep evidence includes at least: `SYNC_ROOT_USER_TOKEN`, `force_root`, `SyncServerRootAdminClient`, `simple_client`, `SYNC_DEVICE_TOKEN`.

---

## 4. Level 1 — Canonical Token Resolver

### 4.1 Scope

Centralize token resolution so all active clients use the same boundary.

### 4.2 Required implementation

Add one canonical resolver, for example:

- `apps/sync_client/token_resolver.py`, or
- internal helper inside `apps/sync_client/client.py` if kept small and tested.

Required API shape:

```python
@dataclass(frozen=True)
class ResolvedSyncIdentity:
    user_token: str
    source: Literal["binding", "session", "root_explicit"]
    is_root: bool
    site_id: str | None

class SyncIdentityNotBoundError(SyncAuthError):
    ...

def resolve_sync_identity(request=None, *, force_root: bool = False, allow_session: bool = True) -> ResolvedSyncIdentity:
    ...
```

Exact class names may differ, but behavior must match.

### 4.3 Required behavior

- If `force_root=True`, return root token only after validating this mode is explicitly requested.
- If request user is authenticated non-superuser:
  1. try `request.user.sync_binding.sync_user_token`;
  2. optionally try session `sync_user_token` only if policy allows session fallback;
  3. if missing, raise controlled missing-binding error.
- If request user is superuser/staff:
  - Do not implicitly use root token for all normal calls.
  - Root token is used only in explicit root/admin call path.
- If request is anonymous and no explicit root mode: raise controlled auth error.
- Never log raw token values.

### 4.4 Acceptance

- There is exactly one tested place where normal user token source priority is defined.
- `SyncServerClient._resolve_user_token()` delegates to that resolver or implements equivalent tested logic.
- Root token fallback warning in `client.py` is removed.

### 4.5 Verification

Add tests for resolver behavior:

- non-superuser with binding -> binding token;
- non-superuser with session token but no binding -> accepted only if session fallback policy says so;
- non-superuser with neither -> controlled auth error, not root;
- superuser without `force_root` -> no implicit root for normal call;
- `force_root=True` -> root token;
- token values absent from logs/errors.

---

## 5. Level 2 — Harden `SyncServerClient`

### 5.1 Scope

Change active low-level transport to enforce Level 1 policy.

### 5.2 Required implementation

File: `apps/sync_client/client.py`

Required changes:

1. Remove regular-user fallback to `self.root_user_token`.
2. Stop treating any authenticated `is_superuser` as automatic root for normal calls.
3. Keep root token only under explicit root mode.
4. Convert missing binding/session token into controlled exception.
5. Apply the chosen `SYNC_DEVICE_TOKEN` policy:
   - preferred: do not raise at initialization when `SYNC_DEVICE_TOKEN` is missing for user-token web calls;
   - include `X-Device-Token` only when configured or when a device-auth endpoint requires it.
6. Keep `SYNC_ROOT_USER_TOKEN` required only when `force_root=True` or root admin client is used.
7. Ensure `build_headers()` never emits empty `X-User-Token`.

### 5.3 Required call-site audit

Every instantiation of `SyncServerClient(..., force_root=True)` must be reviewed:

- Keep only if documented as admin/system.
- Remove from normal user pages where it only decorates data with global names.
- Replace with user-scoped `/auth/sites` or already accessible data where possible.

Specific call sites to address:

- `apps/operations/services.py::OperationPageService.get_all_sites()`.
- `apps/catalog_cache/services.py`.
- `apps/balances/views.py::_get_sites_index()`.
- `apps/common/views.py::SyncHealthCheckView`.

### 5.4 Acceptance

- Non-superuser request with no binding cannot produce root `X-User-Token`.
- Superuser normal request uses binding/session if explicitly bound, or fails controlled; root requires explicit root client/mode.
- Allowed root call sites are documented in the policy inventory.
- Missing `SYNC_DEVICE_TOKEN` behavior matches Level 0 decision.

### 5.5 Verification

Add tests in `apps/sync_client/tests.py` or a new `apps/sync_client/test_auth_boundary.py`:

- `test_non_superuser_no_binding_does_not_fallback_to_root`.
- `test_non_superuser_never_receives_root_token`.
- `test_non_superuser_with_binding_uses_binding_token`.
- `test_superuser_normal_flow_is_not_implicit_root`.
- `test_force_root_uses_root_token_explicitly`.
- `test_missing_device_token_does_not_break_user_token_call` if optional audit policy is chosen.
- Or `test_missing_device_token_fails_with_documented_error` if required audit policy is chosen.

---

## 6. Level 3 — Harden Session Auth and Login Identity Storage

### 6.1 Scope

Ensure `apps/sync_client/session_auth.py` follows the same canonical policy.

### 6.2 Required implementation

File: `apps/sync_client/session_auth.py`

Required changes:

1. `_resolve_sync_user_token()` must not invent root identity for regular users.
2. Any superuser root behavior must be documented as explicit admin/root identity flow.
3. The test named `test_store_syncserver_identity_uses_root_token_fallback` must be renamed or replaced so it does not normalize unsafe fallback.
4. Session legacy key `user_token` must not override the canonical `sync_user_token` policy in unsafe ways.
5. If no token can be resolved, `store_syncserver_identity()` should fail controlled and avoid storing root token/session identity.

### 6.3 Acceptance

- Login/session integration cannot silently store `SYNC_ROOT_USER_TOKEN` for a non-superuser.
- Superuser/root flow is explicit and tested.
- Session state never exposes SyncServer tokens to browser JSON APIs.

### 6.4 Verification

Update/add tests in `apps/users/tests.py`:

- no binding -> identity not stored or controlled error; session does not contain root token;
- non-superuser never stores root token;
- superuser explicit root flow stores root token only when expected;
- existing admin/user tests still pass.

---

## 7. Level 4 — Remove or Isolate `simple_client.py` From Active Auth Flows

### 7.1 Scope

Eliminate legacy client bypass from active auth/business flows.

### 7.2 Required implementation options

Choose one:

#### Option A — migrate `AuthAPI` to canonical client

- Change `apps/sync_client/auth_api.py` to depend on `SyncServerClient`.
- Convert `SyncAPIError` handling to canonical `SyncServerAPIError` exceptions or compatibility wrapper.
- Keep public methods: `get_me`, `get_context`, `get_sites`, `sync_user`, etc.

#### Option B — explicitly legacy-isolate `simple_client.py`

- Rename or mark `SyncClient` as legacy-only.
- Ensure no active imports from `simple_client.py` remain outside legacy tests/docs.
- Add runtime guard or comment that new active code must not import it.

Preferred: Option A.

### 7.3 Acceptance

- `auth_api.py` no longer imports `.simple_client`.
- Grep for `simple_client` shows only docs/legacy tests or no active code.
- There is no second active token resolution algorithm.

### 7.4 Verification

Tests:

- `AuthAPI.get_context()` uses canonical client path.
- `AuthAPI.get_me()` uses canonical client path.
- Static/grep check in QA report: no active import of `simple_client`.

---

## 8. Level 5 — Root Admin Client Boundary

### 8.1 Scope

Keep root-token admin operations but make the boundary explicit.

### 8.2 Required implementation

File: `apps/sync_client/root_admin_client.py`

Required changes:

1. Document that this client is for Django staff/superuser admin or system jobs only.
2. Do not expose this client to browser-facing BFF endpoints for ordinary users.
3. Apply Level 0 `SYNC_DEVICE_TOKEN` policy.
4. Ensure logs redact tokens.
5. Optionally require caller proof/context if instantiated from request flows, e.g. `request.user.is_staff` checked in service layer.

### 8.3 Acceptance

- Root admin client remains available for approved admin flows.
- Normal BFF views/services do not instantiate it or root mode unless allowlisted.
- Staff/superuser root flow is covered by tests.

### 8.4 Verification

Tests:

- `SyncServerRootAdminClient` sends root token when configured.
- Missing root token fails only in root/admin path.
- Normal user cannot trigger root admin path.

---

## 9. Level 6 — BFF/View Error Handling

### 9.1 Scope

Make missing binding errors safe and user-visible without leaking internals.

### 9.2 Required implementation

- Ensure `SyncAuthError`, `SyncForbiddenError`, or new missing-binding exception maps to 401/403/controlled error in:
  - BFF JSON endpoints;
  - Django page services;
  - auth/session flows.
- Avoid 500s for expected “user not bound to SyncServer” cases.
- Do not expose token values in messages.

### 9.3 Acceptance

- No binding -> controlled response.
- Browser JSON APIs do not leak SyncServer token values.
- HTML pages show actionable message or redirect/admin instruction.

### 9.4 Verification

Django integration tests using `Client`/`RequestFactory`:

- authenticated user without binding -> 401/403 or controlled page error;
- authenticated user with binding -> normal flow;
- anonymous user -> login/auth error according to existing view policy.

---

## 10. Required Test Ladder

### 10.1 Static checks

Required command after implementation:

```powershell
python manage.py check
```

If project uses lint/type checks, run the existing configured command and document it.

### 10.2 Unit/component tests

Required command:

```powershell
python manage.py test apps.sync_client apps.users
```

Must cover:

- token resolver;
- canonical client header building;
- missing binding behavior;
- root explicit behavior;
- device token policy;
- simple client isolation.

### 10.3 Django integration tests

Required command:

```powershell
python manage.py test apps.sync_client apps.users apps.operations apps.balances apps.common
```

Must cover affected views/services that previously used `force_root=True`.

### 10.4 Full regression

Required command:

```powershell
python manage.py test
```

### 10.5 Real stand smoke

Runtime auth behavior should be smoked against a real SyncServer stand when available.

Minimum stand:

- SyncServer FastAPI app.
- PostgreSQL test DB migrated with Alembic.
- Root user token.
- Non-root user token with site scope.
- Django user bound to non-root SyncServer user.
- Django user without binding.
- Django superuser/staff for explicit root/admin flow.

Environment variable names only:

- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN` if chosen policy requires or audit-includes it
- `SYNC_TEST_USER_TOKEN`
- `SYNC_TEST_SITE_ID`

Smoke scenarios:

1. Non-bound normal Django user calls a BFF/page path that needs SyncServer -> controlled 401/403/error, not root response.
2. Bound normal Django user calls the same path -> request has bound user token.
3. Non-superuser cannot trigger root admin client/root token path.
4. Staff/superuser explicit admin/root flow succeeds.
5. If `SYNC_DEVICE_TOKEN` is absent and optional policy is chosen, normal user-token calls still work.

Use background PTY sessions for long-running Django/SyncServer stands.

### 10.6 UI automation

No Playwright requirement for this TZ unless a browser/admin UI behavior is changed.

If admin UI flow is changed, add one browser smoke or Django admin client test proving staff/superuser flow is explicit.

Otherwise leave checklist item `UI automation` unchecked with reason: “auth boundary is covered by Django integration tests; no UI behavior changed.”

---

## 11. Acceptance Criteria

This TZ is complete when all are true:

1. `SyncServerClient` no longer falls back from a regular Django user to `SYNC_ROOT_USER_TOKEN`.
2. Missing binding/session token yields controlled auth/forbidden/missing-binding error.
3. Non-superuser can never receive root token through canonical user flow.
4. Superuser/staff root usage is explicit through `force_root=True`, `SyncServerRootAdminClient`, or documented admin/system allowlist.
5. `SYNC_DEVICE_TOKEN` policy is documented and code matches it.
6. `simple_client.py` is not in active auth flow, or is clearly isolated legacy-only.
7. Tests cover no-binding, non-superuser, explicit root, device-token policy, and simple-client isolation.
8. Full `python manage.py test` passes or failures unrelated to this TZ are documented with owner/blocker.
9. QA verifier reviews evidence before final checklist acceptance.

---

## 12. Evidence Table Template

Executor report must include:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static check | `python manage.py check` | pass/fail/skipped | log/summary |
| Unit tests | `python manage.py test apps.sync_client apps.users` | pass/fail/skipped | log/summary |
| Integration tests | `python manage.py test apps.sync_client apps.users apps.operations apps.balances apps.common` | pass/fail/skipped | log/summary |
| Full regression | `python manage.py test` | pass/fail/skipped | log/summary |
| Stand smoke | Django + SyncServer stand | pass/fail/skipped | URL/log note, no secrets |
| Root grep audit | grep `SYNC_ROOT_USER_TOKEN`, `force_root`, `simple_client` | pass/fail | classified findings |
| Device token policy | doc + tests | pass/fail | policy path/test name |

---

## 13. Routing Guidance

- Use `django-bff` for implementation in `Warehouse_web`.
- Use `qa-verifier` after implementation to review evidence and root-use audit.
- Use `docs-curator` only if broader active docs need updates beyond the policy note.
- Use `syncserver-backend` only if a SyncServer auth contract is ambiguous or missing.
