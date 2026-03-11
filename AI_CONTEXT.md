# AI_CONTEXT

## System architecture
- Проект: Django SSR web-client.
- Архитектурный стиль: layered modular monolith.
- Интеграция: SyncServer по HTTP через единый клиент.

## Backend rules
- Для каталога не обращаться к внешнему API напрямую из views; использовать `CatalogService`.
- Ошибки SyncServer обрабатывать через `ServiceResult` (`ok`, `not_found`, `server_unavailable`, `form_error`).
- Ролевые проверки выполнять через `apps.common.permissions`.

## Database rules
- Локальная БД: данные Django (auth/admin/sessions) и локальные сущности проекта.
- Каталог (`Category`, `Unit`, `Item`) в runtime считается внешним доменом SyncServer.
- Не предлагать решения, где мастер-данные каталога редактируются напрямую через Django ORM как основной путь.

## Layered architecture
- API/Application: `urls.py` + `views.py`
- Service: `apps/catalog/services.py`
- Data/Integration: `apps/integration/syncserver_client.py`
- Domain models: `apps/catalog/models.py`, `apps/users/models.py`

## Client rules
- UI server-rendered (Django Templates), без выделенного SPA слоя.
- Основные пользовательские интерфейсы: `/client/` и `/catalog/*`.

## Architecture constraints
- SyncServer headers обязательны: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`.
- Нет прямой зависимости views от httpx-клиента.
- Модуль `documents` пока не содержит рабочей бизнес-логики.
