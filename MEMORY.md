# MEMORY

## Architectural invariants
- SyncServer — единственный source of truth для warehouse domain.
- Django auth нужен только для technical root/staff/admin слоя.
- Legacy `UserProfile/Site/Role` не должен блокировать вход или работу superuser/staff.

## Current transition status
- Legacy signals не автоподключаются в `apps.users.apps.UsersConfig.ready`.
- Permissions fallback устойчив к отсутствию profile.
- Root panel управляет domain users через SyncServer API, не через Django ORM.

## UI status
- Root: отдельный control panel для users/roles/sites.
- Chief: справочники каталога через API-first `apps.catalog`.
- Storekeeper: каталог, остатки, операции, создание операции.
