# Django Safe Refactor Phase 1

Date: 2026-03-19
Status: Safe refactor completed with import validation only
Runtime status: NOT VERIFIED

## 1. Changed files list

- `apps/common/mixins.py`
- `apps/operations/views.py`
- `apps/balances/views.py`
- `apps/admin_panel/views.py`
- `apps/admin_panel/api_views.py`
- `apps/users/views.py`
- `apps/users/views_with_error_handling.py`
- `apps/common/api_error_handler.py`
- `apps/sync_client/exceptions.py`
- `apps/sync_client/users_api.py`
- `apps/sync_client/sites_api.py`
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`
- `apps/sync_client/simple_client.py`

## 2. What was moved / unified

### Shared mixins/helpers moved to common module

Moved shared view context setup into:
- `apps/common/mixins.py`

Now this module contains:
- `SyncContextMixin`
- `SyncAdminMixin`

Updated active imports so feature apps no longer import each other just to reuse these mixins.

### Exception handling unified

Canonical exception name in active code paths is now:
- `SyncServerAPIError`

Compatibility kept via alias:
- `SyncAPIError = SyncServerAPIError` in `apps/sync_client/exceptions.py`

Updated active shared handling and active admin API views to use `SyncServerAPIError` directly.

### API wrapper imports aligned

Aligned active API wrapper modules to import exceptions from the canonical exception module:
- `apps/sync_client/users_api.py`
- `apps/sync_client/sites_api.py`
- `apps/sync_client/operations_api.py`
- `apps/sync_client/balances_api.py`

### Legacy client status clarified

Canonical runtime client is now explicitly treated as:
- `apps.sync_client.client.SyncServerClient`

Legacy module:
- `apps/sync_client/simple_client.py`

was not removed, but was explicitly marked as deprecated/legacy in the module docstring.

## 3. Canonical API client

Canonical active runtime client:
- `apps.sync_client.client.SyncServerClient`

Reason:
- it is already the client used by active Django runtime views for users, operations, balances, catalog/client integrations, and the shared mixins now initialize this client centrally.

## 4. Canonical exception naming

Canonical exception naming in active runtime paths:
- `SyncServerAPIError`

Backward compatibility retained:
- `SyncAPIError` remains available only as a compatibility alias in `apps/sync_client/exceptions.py`

## 5. Cyclic imports removed

Removed cross-app imports caused by shared mixin reuse:
- `apps/balances/views.py` no longer imports `SyncContextMixin` from `apps/operations/views.py`
- `apps/admin_panel/views.py` no longer imports `SyncContextMixin` from `apps/operations/views.py`
- `apps/admin_panel/api_views.py` no longer imports `SyncContextMixin` from `apps/operations/views.py`
- `apps/users/views.py` no longer owns a local `SyncAdminMixin`; shared mixin now lives in `apps/common/mixins.py`
- `apps/users/views_with_error_handling.py` no longer owns a local `SyncAdminMixin`; shared mixin now lives in `apps/common/mixins.py`
- `apps/operations/views.py` no longer serves as the source module for reusable shared mixins

Result:
- `apps/users`, `apps/operations`, `apps/balances`, `apps/admin_panel` no longer depend on each other for shared view-context mixins.

## 6. Validation performed

Performed:
- Python compile validation (`py_compile`) for touched modules: PASSED
- Django import validation after `django.setup()` for key refactored modules: PASSED
- Refactored modules imported without cyclic import crash: PASSED

Validated imports included:
- `apps.common.mixins`
- `apps.operations.views`
- `apps.balances.views`
- `apps.users.views`
- `apps.users.views_with_error_handling`
- `apps.admin_panel.views`
- `apps.admin_panel.api_views`

What this means:
- import-time integrity is verified
- Django module loading for the refactored layer is verified

What this does NOT mean:
- end-to-end runtime behavior against real SyncServer is NOT VERIFIED

## 7. What remains for next phase

Recommended next-phase work:
- real test-stand validation against SyncServer for users/sites/operations/balances flows
- template stabilization after refactor confirmation
- catalog completion on top of stabilized integration layer
- auth/session flow verification under real login/logout and site-switch scenarios
- broader cleanup of remaining legacy `SyncAPIError` references in helper/legacy/auth modules if and only if done together with runtime validation
- optional follow-up pass to reduce duplicate/legacy view modules after confirming which ones are still active

## 8. Explicit statement: what was NOT changed

The following were intentionally NOT changed:
- SyncServer API contracts
- Django auth model design
- business logic of operations
- business logic of balances
- business logic of catalog
- Docker/CI/env configuration
- SyncServer endpoint semantics
- session auth architecture redesign
- domain behavior of users/sites workflows

Also not done in this phase:
- no endpoint contract rewrites
- no backend redesign
- no ORM redesign
- no temporary/debug/old files created

## 9. What still requires real runtime testing

Still requires real runtime validation:
- users pages and CRUD flows
- sites pages and CRUD flows
- operations pages and submit/cancel flows
- balances list/summary/by-site flows
- session auth integration
- site switching with acting site context
- SyncServer error rendering in templates/messages

Runtime verification status for the above:
- NOT VERIFIED

## 10. Notes and limitations

There are still legacy/compatibility modules in the repository that reference `SyncClient` / `SyncAPIError`, especially around auth/session helper flows and example modules.

In this phase they were not redesigned or removed because the task required a safe refactor without changing auth design or business logic. The active Django integration layer was stabilized around `SyncServerClient` and `SyncServerAPIError`, while compatibility was preserved for legacy paths.
